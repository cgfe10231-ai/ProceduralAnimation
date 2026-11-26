# TASK 10-B / fix-3 证据清单 (Evidence Manifest)

- **基线分支**：`audit/task-10-b-9`
- **基线 Commit HEAD**：`70ae9478727354accc17491f08f23b856c33902c`
- **测试环境**：
  - 操作系统：Windows (PowerShell)
  - 执行引擎：Blender 5.1.1 (build date: `2026-04-14 01:37:22`, hash: `b70da489d7f4`, Release)
  - 宿主 Python：Blender 内置 Python 3.11.x
  - 测试框架：Python `unittest` 标准库 (精确方法选择执行)
- **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (APPROVED, 2026-11-11)

---

## 1. 六项测试执行结果概览

| 编号 | 测试用例方法名 | 状态 | 退出码 | 耗时 |
| :---: | :--- | :---: | :---: | :---: |
| **TEST-244** | `test_244_cleanup_retry_does_not_clear_concurrent_failed_isolation` | **PASS** | 0 | 0.613s |
| **TEST-136** | `test_136_cleanup_pending_and_failed_isolation_strictly_separated` | **PASS** | 0 | 0.259s |
| **TEST-242** | `test_242_fault_after_logical_commit_before_layer6_enters_cleanup_pending_no_rollback` | **PASS** | 0 | 0.219s |
| **TEST-243** | `test_243_repeated_cleanup_after_success_is_idempotent_no_ghost_pending` | **PASS** | 0 | 0.229s |
| **TEST-163** | `test_163_unknown_liveness_preserves_failed_isolation` | **PASS** | 0 | 0.236s |
| **TEST-131** | `test_131_verified_recovery_deisolates_failed_b_and_failed_c_and_restores_admission` | **PASS** | 0 | 0.232s |

- **总执行数**：6
- **PASS 数量**：6
- **FAIL 数量**：0
- **ERROR 数量**：0
- **未执行数量**：0

---

## 2. 实际日志来源与保真说明

- **日志来源**：
  上述六项测试真实执行于前一轮（TEST ONLY 阶段，时间区间 `2026-11-16T15:02:14+08:00` 至 `2026-11-16T15:05:35+08:00`）。
  原始运行输出、进程退出码及 Traceback 完整保存在当前对话实时上下文及会话转录日志中（`transcript.jsonl` / `transcript_full.jsonl`）。
- **保真说明**：
  `test_execution.log` 中记录的控制台文本为命令实际执行产生的原始 stdout/stderr 输出，100% 保持原文，无任何删减、篡改或润色。
- **证据缺失与缺口**：
  无证据缺失。六项测试均有完整执行命令、精确耗时、进程退出码与原始控制台输出支撑。

---

## 3. 证据文件清单

本证据目录包含以下三个归档文件：

1. [`test_results.md`](./test_results.md)：逐项测试的详细参数、执行命令、执行时间、判定结果与异常捕获说明。
2. [`test_execution.log`](./test_execution.log)：六项测试的完整原始控制台标准输出记录。
3. [`evidence_manifest.md`](./evidence_manifest.md)：本清单文件，汇总环境、HEAD、结果概览与真实性背书。

---

## 4. 测试前后 Git 状态

- **测试前 HEAD**：`70ae9478727354accc17491f08f23b856c33902c`
- **测试后 HEAD**：`70ae9478727354accc17491f08f23b856c33902c`
- **工作区状态**：
  - `git diff --exit-code` 退出码：`0`（零生产及测试源码 Diff）
  - `git diff --cached --exit-code` 退出码：`0`（零暂存区 Diff）
  - 生产代码（`src/`）与测试代码（`tests/`）在测试前后均未发生任何改动。
  - 七个历史受保护未跟踪文件保持完整保留。

---

## 5. 额外测试声明

本轮及测试阶段严格遵守指令范围，**未执行**任何额外测试（包括但不限于 quick/physics/motion/full 四级统一回归、压力测试、动画导出测试或其他 fix 组测试），全部执行数量严格锁定为 fix-3 的六项冻结测试。
