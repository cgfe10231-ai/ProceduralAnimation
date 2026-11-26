# TASK 10-B / fix-7 — Collection Relationship Targeted Validation Report

## 1. 基线与环境信息

- **仓库**：`cgfe10231-ai/ProceduralAnimation`
- **分支**：`audit/task-10-b-9`
- **测试前冻结 HEAD**：`7c7fd998c18fef821f6b9303f9338947ff8eed0f`
- **`tests/test_task10b_transaction_atomicity.py` Git Blob**：`1bfb615129a0f83521e6c49cd2802456bb87bd15`
- **`src/rig/arm_ik.py` Git Blob**：`bedbcda220af8d47d11b5400de8a56375019eba4`
- **Blender 可执行文件**：`C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
- **Blender 版本**：`Blender 5.1.1` (`ProductVersion: 5.1`, `FileVersion: 5.1`)
- **内嵌 Python 版本**：`Python 3.13.9`

---

## 2. 执行汇总与真实退出码

- **目标测试类**：`TestArmIKTransactionAtomicity`
- **目标测试范围**：`TEST-225`～`TEST-233`（共 9 项）
- **实际发现 / 实际执行数量**：`0` 项（因 PowerShell 启动器 `ProcessStartInfo.ArgumentList` 空引用异常，命令行参数未传入 Blender 进程）
- **统计计数**：
  - `PASS`：`0`
  - `FAIL`：`0`
  - `ERROR`：`0`
  - `SKIPPED`：`0`
  - `NOT_RUN`：`9`
- **Blender 进程真实退出码**：`0`（无参启动后直接退出，未执行 `--background --python-exit-code 1 --python-expr`）
- **必需成功标记核对**：
  - `FIX7_COLLECTION_SELECTED [225, 226, 227, 228, 229, 230, 231, 232, 233]`：**未出现**
  - `Ran 9 tests` / `OK`：**未出现**
  - `FIX7_COLLECTION_EXECUTED 9`：**未出现**
  - `FIX7_COLLECTION_PASS True`：**未出现**
- **判定结果**：**STOPPED ON RUNNER EXCEPTION (`FIX7_COLLECTION_TARGETED_FAILED_WAITING_FOR_CHATGPT_AUDIT`)**
  - 依据任务规范第 5 节（“4. 不自动重试”、“任一条件不成立，立即停止”）、第 7 节（“如果出现：... Blender 运行器异常；立即停止。禁止：... 自动重跑”）及第 8 节（“该目录必须事先不存在。如果已经存在，立即停止，不得覆盖”），首次启动出现运行器异常后立即停止，**未执行任何重跑或覆盖**。

---

## 3. 九项测试实际执行状态

| 测试编号 | 测试方法名 | 实际状态 |
|---|---|---|
| `TEST-225` | `test_225_collection_child_link_rollback_unlinks` | `NOT_RUN` |
| `TEST-226` | `test_226_collection_child_link_idempotent_when_already_linked` | `NOT_RUN` |
| `TEST-227` | `test_227_collection_child_link_fault_before_c_api_no_effect` | `NOT_RUN` |
| `TEST-228` | `test_228_collection_child_link_fault_before_confirm_reverts` | `NOT_RUN` |
| `TEST-229` | `test_229_authorized_unlinked_child_collection_restored_on_rollback` | `NOT_RUN` |
| `TEST-230` | `test_230_external_second_parent_preserved_on_rollback` | `NOT_RUN` |
| `TEST-231` | `test_231_unauthorized_parent_collection_rejected` | `NOT_RUN` |
| `TEST-232` | `test_232_unauthorized_pre_existing_child_collection_rejected` | `NOT_RUN` |
| `TEST-233` | `test_233_joint_bilateral_rollback_parent_collection_child_constraint_targets` | `NOT_RUN` |

---

## 4. 完整日志路径

- **标准输出日志**：`docs/evidence/fix-7/collection_targeted/test_stdout.log`
- **标准错误日志**：`docs/evidence/fix-7/collection_targeted/test_stderr.log`

### `test_stdout.log` 原始内容

```text
00:12.453  blend            | Saved session recovery to "C:\Users\64701\AppData\Local\Temp\quit.blend"

Blender quit
```

### `test_stderr.log` 原始内容

```text
(empty, 0 bytes)
```

---

## 5. 实际异常与完整调用栈（运行器启动器异常）

在 Windows PowerShell 5.1 (`.NET Framework`) 中，`System.Diagnostics.ProcessStartInfo` 不包含 `.NET Core` 的 `ArgumentList` 属性（`$psi.ArgumentList` 为 `$null`，需使用 `$psi.Arguments` 字符串属性传参）。调用 `[void]$psi.ArgumentList.Add(...)` 触发了 5 次 PowerShell `InvokeMethodOnNull` 异常，导致 `$proc.Start()` 以空参数启动了 `blender.exe`：

```text
You cannot call a method on a null-valued expression.
At line:101 char:1
+ [void]$psi.ArgumentList.Add("--background")
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidOperation: (:) [], RuntimeException
    + FullyQualifiedErrorId : InvokeMethodOnNull
 
You cannot call a method on a null-valued expression.
At line:102 char:1
+ [void]$psi.ArgumentList.Add("--python-exit-code")
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidOperation: (:) [], RuntimeException
    + FullyQualifiedErrorId : InvokeMethodOnNull
 
You cannot call a method on a null-valued expression.
At line:103 char:1
+ [void]$psi.ArgumentList.Add("1")
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidOperation: (:) [], RuntimeException
    + FullyQualifiedErrorId : InvokeMethodOnNull
 
You cannot call a method on a null-valued expression.
At line:104 char:1
+ [void]$psi.ArgumentList.Add("--python-expr")
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidOperation: (:) [], RuntimeException
    + FullyQualifiedErrorId : InvokeMethodOnNull
 
You cannot call a method on a null-valued expression.
At line:105 char:1
+ [void]$psi.ArgumentList.Add($pyExpr)
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidOperation: (:) [], RuntimeException
    + FullyQualifiedErrorId : InvokeMethodOnNull
```

---

## 6. Git 文件变更核查结果

- `git diff --exit-code`：`0`（已跟踪源码零修改）
- `git diff --cached --exit-code`：`0`（暂存前为空）
- `tests/test_task10b_transaction_atomicity.py` Git Blob：`1bfb615129a0f83521e6c49cd2802456bb87bd15`（未变）
- `src/rig/arm_ik.py` Git Blob：`bedbcda220af8d47d11b5400de8a56375019eba4`（未变）
- 历史未跟踪文件（7 项）与历史 `docs/evidence/fix-7/` 证据均保持原状，未受触碰。
- 新增证据目录：`docs/evidence/fix-7/collection_targeted/`（包含 `test_report.md`、`test_stdout.log`、`test_stderr.log`）。
