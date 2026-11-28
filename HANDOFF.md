# HANDOFF — 当前项目交接卡片

> 核验日期：2026-11-28；Task 12 / PKG-5 冻结生产基线：`eee276b39d204ccd46f4c17f37a09ec483bfcbae`，冻结测试基线：`90f4628a0c4212f4bb0468941cdde362cd68bef2`，最终验收证据提交：`e15d342b805ef45e7d54db2edf1c2804973e81a7`（收归合入自 `task/12`）；Task 7B-1 验收证据提交：`fcb35bd58eeb4e5300d5f3b28e3615be8cb7c946`、Task 7B-2 验收证据提交：`a92280bbcb2243f0b43edd10b61bbadb39c72869`（保留于 `task/7b-1` → `task/7b-2` → `task/7b-3` → `task/7b-4` 连续子阶段分支，已合入 `master`）；Task 11 历史合入：`added88a7e27eaaa6d1644473d560c5dcf45bc80` / `07aec5d8d35e5d77ff956f160840d1c2491b770e`；10-D 历史合入 `824c52ec73f86aa3d08245a58297118cb4a9f110` / `7f14ff722caecadec555194cc7d08f454c94c6c8`；10-C 历史合入 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`；10-B 历史合入 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`。 Task 7B-3 专项最终证据：`d9862ada5c392080a03efb38ea7f2e90201580d2`。 冻结执行基线 `a3720711bfdae1e759485c13f4fc3379be951534`；证据提交 `4a2f4a0743803e1cb747f0927b236dd357694c39`、`1cc2a4b18a309723dc5a0cae2a4e981e2e263f82`，证据目录 `docs/evidence/7b-4/final_acceptance/`、`docs/evidence/7b-4/final_acceptance_round2/`。
> 本文件是摘要，不授予任务准入；须以 `PROJECT_STATE.md`、`ARCHITECTURE_SYNC.md`、`OPEN_FINDINGS.md` 及 Git 实况核对。

## 当前交接状态
- **Task 12 / PKG-5**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（`Task 12-A/B/C/D` `COMPLETED`，`Task 12-D BUG-01` `CLOSED`）。
- **Task 7B-1**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（Blender 5.1.1 专项 `T01–T12` `12 PASS / 0 FAIL / 0 SKIP / 0 NOT_RUN`，退出码 `0`；`BUG-01 CLOSED`；生产源码零修改，新增生产函数及模块 `0`；证据提交 `fcb35bd58eeb4e5300d5f3b28e3615be8cb7c946`，证据目录 `docs/evidence/7b-1/verification/`；**已合入 `master`**）。
- **Task 7B-2**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（Blender 5.1.1 专项 `T01–T14` 全部通过，`14 PASS / 0 FAIL / 0 SKIP / 0 NOT_RUN`，退出码 `0`；`BUG-01`、`BUG-02` `CLOSED`；证据提交 `a92280bbcb2243f0b43edd10b61bbadb39c72869`，证据目录 `docs/evidence/7b-2/verification/`；**已合入 `master`**）。
- `Task 7B-3`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Blender 5.1.1 专项 T01–T20 两轮累计 20/20 PASS；第一轮 T01–T15 PASS、T16 FAIL、T17–T20 NOT_RUN，退出码 1；BUG-03 修复后第二轮 T16–T20 全部 PASS，退出码 0；BUG-01、BUG-02、BUG-03 CLOSED；生产源码零修改。第一轮证据提交 `238383869203aaa39218d2695c2592bd80d44a2e`，`docs/evidence/7b-3/verification/`；第二轮证据提交 `d9862ada5c392080a03efb38ea7f2e90201580d2`，`docs/evidence/7b-3/verification_round2/`。
- `Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Blender 5.1.1 联合专项 46/46 PASS（7B-1 12/12、7B-2 14/14、7B-3 20/20），独立相关回归 47/47 PASS；四级回归 quick 19/19、physics 27/27、motion 12/12、full 42/42，最终各组 rc=0、FAILED=SKIPPED=NOT_RUN=0。第一轮 physics 因隔离资产遗漏停止，补齐后通过，原始失败证据保留。源训练场 SHA-256 不变；AUTOMATED_PASS 不等于人工视觉验收。冻结执行基线 `a3720711bfdae1e759485c13f4fc3379be951534`；证据提交 `4a2f4a0743803e1cb747f0927b236dd357694c39`、`1cc2a4b18a309723dc5a0cae2a4e981e2e263f82`，证据目录 `docs/evidence/7b-4/final_acceptance/`、`docs/evidence/7b-4/final_acceptance_round2/`。Phase 7B 已收归 `master`。下一节点 `Phase 7C`：`NOT AUTHORIZED`（仅 ChatGPT 独立只读审计，尚未批准实施）。
- **原 16 项历史 Finding**：**16 CLOSED / 0 OPEN**；**21 项冻结记录**与 **12 项架构合同** 保持原定义。

| 子节点 | 实现边界与关键 Blob | 状态 |
|---|---|---|
| 12-A (WBC) | `src/motion/whole_body_controller.py` (`230a86acaa92b580c5c0aad0e0cdacd7df224a7a`)：ROM 截断后重测最终四肢/CoM 反馈、真实请求误差 `ROM_CONFLICT`、单帧状态捕获与失败原子回滚 | `COMPLETED` |
| 12-B (Bridge) | `src/motion/kinematic_bridge.py` (`4f9cc856b9c9b34c59dd4c6a4f0cee1e1d86ef96`)：`effective_dt` 准入门禁、WBC/ContactModel 失败禁止提交跨帧 7 项状态（允许诊断返回、不污染后续帧） | `COMPLETED` |
| 12-C (所有权) | 删除废弃 `_reconcile_post_rom_feedback()`（ROM 后最终反馈归 WBC 独占），`body_kinematics.py` (`e204793ca3a326a798f75a66e24e98a945e53be7`) 与 `body_inertia.py` (`0cd7efadf265072fd1665615815792f41b792f1b`) 遥测状态所有权收敛 | `COMPLETED` |
| 12-D & BUG-01 | 完成联合专项、历史合同复验与四级 `--fail-fast` 最终回归；`tests/verify_task6gc_r3b1_bridge.py` (`eb99144187291e8acd3ad2f3399fc955096c9e45`) `test_10_variable_dt_and_kinematic_scaling()` 修复直腿超限并隔离零 `dt` 测试 | `COMPLETED` (`BUG-01 CLOSED`) |

## Task 12 最终联合验收证据（`docs/evidence/12/final_acceptance/`）
| 项目 | 实测结果 | 证据路径与说明 |
|---|---|---|
| WBC A01–A20 | **20/20 PASS** (`rc=0`) | `phase1_task12/wbc_results.json` |
| Bridge B01–B19 | **19/19 PASS** (`rc=0`) | `phase1_task12/bridge_results.json`（保留 B19 部分 F-Curve 残余风险记录） |
| C01–C16 及 10-C Retirement | **17/17 PASS** (`rc=0`) | `phase1_task12/telemetry_results.json` |
| 连续生产链 | **PASS** (`rc=0`) | `phase1_task12/continuous_results.json`（5 种动作、`296f` 四种双臂 FK/IK、10 次锁足切换、`Reset` 与不等步长失败重试 `dt=0.06s`） |
| B20 场景独立重开 | **2/2 PASS** (`rc=0`) | `phase1_task12/reopen_results.json`、`phase1_task12/reopen_artifacts/`（`OWNER WAIVED`） |
| 历史合同联合复验 | WBC `6/6`、10-D T01–T15 `15/15`、Task 11 FootLock `38/38`、09-B `27/27`、地面高度 `20/20`、初始化与重置 `6/6` | `phase2_historical/`（含原始 `.log` 与 JSON） |
| `quick` / `physics` / `motion` / `full` (`--fail-fast`) | **19/19** (16P+3AP)、**27/27** (24P+3AP，含历史 Bridge **14/14 PASS**)、**12/12** (6P+6AP)、**42/42** (33P+9AP) | `phase3_regression/regression_*/test_report.json`（全部 `rc=0`，`FAILED=SKIPPED=NOT_RUN=0`） |

## 保留风险、验收边界与纪律
1. B19 底层关键帧写入故障可产生部分 F-Curve 残留，七项 Bridge 提交状态保持完整，但不宣称 Blender 关键帧写入完全事务原子化。
2. 10-D 历史复验 JSON 的 `head` 字段引用旧固定常量，实际 Worker 使用当前仓库目录；不得篡改原始报告。
3. Task 12 人工视觉验收登记为 `OWNER WAIVED`。
4. 历史九项人工视觉待办保持原登记（10-D 两份场景 `output/task10d_centralized_whole_body.blend` 与 `output/task10d_running_whole_body.blend` 保持原验收登记）。
5. 19 骨骼运动学管线与 6-DOF 数值动力学管线仍然独立，尚未完成 7C 合流。
- 历史归档目录：Task 7B-4 `docs/evidence/7b-4/final_acceptance/`、`docs/evidence/7b-4/final_acceptance_round2/`（`1cc2a4b1`）；Task 7B-3 `docs/evidence/7b-3/verification/` 与 `docs/evidence/7b-3/verification_round2/`（`d9862ada`）；Task 7B-2 `docs/evidence/7b-2/verification/`（`a92280bb`）；Task 7B-1 `docs/evidence/7b-1/verification/`（`fcb35bd5`）；Task 12 BUG-01 过程保全 `docs/evidence/12/unified_verification/`（`c9c9a2d`）；Task 11 `docs/evidence/11/unified_verification/`；10-D `docs/evidence/10-d/`；10-C `docs/evidence/10-c-integration/`；10-B `docs/evidence/10b_sixlayer_split/regression/`。
- Phase 7B 已验收并收归 `master`；执行 Agent 本轮仅完成获授权的主干收归与状态同步，结束后恢复 Markdown 默认只读。Phase 7C 由 ChatGPT 先行只读审计，实施另行批准。
