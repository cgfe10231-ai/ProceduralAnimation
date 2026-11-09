# TASK 10-B-15 (Round 6/6: F-06 / CONTRACT-10 / 十二项合同证据收束) Deferred Observations

> **基线 Commit**: `56fcf62630b331b3e6c7233351d7ddc263be9919`
> **分支**: `audit/task-10-b-9`
> **创建时间**: 2026-11-10
> **性质**: 真实缺陷观察与历史遗留项归档（只读冻结，严禁为追求全绿篡改测试或生产代码）

---

## 1. 历史未决遗留项清单 (11 项维持 OPEN)

在 TASK 10-B-15 Round 1/6 至 Round 5/6 迭代中，根据任务授权约束，以下 11 项技术遗留项被严格冻结，未在生产代码中做越权处理，全部维持 **OPEN** 状态：

| 编号 | 来源轮次 | 描述 | 状态 | 冻结原因与架构说明 |
|---|---|---|---|---|
| **R1-TAIL-01** | Round 1/6 | Type B 授权来源真实性校验 | **OPEN** | DataBlock 授权容器未校验授权发起方的真实身份令牌，允许外部构造伪造授权 |
| **R1-TAIL-02** | Round 1/6 | Type A 合法授权删除完整性验证 | **OPEN** | 正常生命周期终结时合法的 DataBlock 删除缺少全生命周期覆盖测试 |
| **R1-TAIL-03** | Round 1/6 | 授权删除异常分支场景覆盖 | **OPEN** | `_authorized_delete_datablock()` 遇到受保护只读数据块时的异常传播路径未穷尽 |
| **R2-TAIL-01** | Round 2/6 | 非 Empty 类型重命名冲突规避 | **OPEN** | 当存在非 Empty 且重名冲突时，重命名暂存策略可能与外部命名产生二次冲突 |
| **R2-TAIL-02** | Round 2/6 | 暂存数据块生命周期跟踪 | **OPEN** | 暂存的错误类型对象在事务提交后的彻底清理逻辑未与统一事务完全对接 |
| **R3-TAIL-01** | Round 3/6 | 历史约束非托管状态恢复 | **OPEN** | 事务开始前已存在的外部非托管约束在发生回滚时的无害恢复合同验证 |
| **R4-TAIL-01** | Round 4/6 | 循环挂载关系检测 | **OPEN** | Object Parent / Collection 挂载时的环形依赖预防检测（DAG 成环） |
| **R4-TAIL-02** | Round 4/6 | 跨 Scene / 外部 ViewLayer 挂载保护 | **OPEN** | 多场景/多视图层上下文下的集合所有权与解绑边界隔离 |
| **R4-TAIL-03** | Round 4/6 | 多级父子回滚逆序执行健壮性 | **OPEN** | 超过 3 级深度的复杂嵌套集合在多重异常下的逆序恢复完整性 |
| **R4-TAIL-04** | Round 4/6 | 外部引用计数字典同步更新 | **OPEN** | 集合解绑后外部引用计数的原子化增减与垃圾收集时序 |
| **R4-TAIL-05** | Round 4/6 | 极端变换矩阵逆矩阵非数值防护 | **OPEN** | 矩阵逆运算遇浮点奇异退化时的安全降级分支 |

---

## 2. CONTRACT-10 WBC / Arm IK 单帧失败边界真实缺陷观察

在 Round 6/6 中，执行了新增的 CONTRACT-10 专项测试套件 `tests/test_task10b_wbc_failure_contract.py`。
测试结果表明，**CONTRACT10-01**（正常双臂反馈）与 **CONTRACT10-05**（不可达目标反馈）**PASS**，而 **CONTRACT10-02, CONTRACT10-03, CONTRACT10-04, CONTRACT10-06** 4 项测试发生真实断言失败（**TRUE FAIL**）。

这些失败真实暴露了当前 `WholeBodyController` 与 `Arm IK` 子系统之间的架构性缺陷：**WBC 缺少跨子系统单帧事务管理，上层写入未受保护，Arm IK 失败或隔离拒绝时 WBC 已派发的 Root/Pelvis/Spine 与先行手臂写入发生污染残留。**

### 2.1 缺陷观察一：CONTRACT10-02 (CLEANUP_PENDING 隔离下的 WBC 污染)

- **测试用例**: `test_contract10_02_pending_cleanup_isolation_propagation_to_wbc`
- **预期行为**: 当 Armature 处于 `CLEANUP_PENDING` 隔离状态时，Arm IK 事务入口拒绝准入，WBC 执行帧操作应当失败并保证全身状态零污染（Root 保持 `(0.0, -8.0, 0.0)`）。
- **实际行为**: WBC 在派发 Hand IK 之前已经修改了 `root.location` (`(0.0, -7.0, 0.0)`)。虽然 Arm IK 抛出准入拒绝异常，但 WBC 并没有帧级回滚机制，导致 Root 坐标被永久污染。
- **差异比对**:
  ```text
  AssertionError: Tuples differ: (0.0, -7.0, 0.0) != (0.0, -8.0, 0.0)
  First differing element 1:
  -7.0
  -8.0
  - (0.0, -7.0, 0.0)
  + (0.0, -8.0, 0.0)
  : CONTRACT-10 DEFECT: Root position partially modified ((0.0, -7.0, 0.0) != (0.0, -8.0, 0.0)) after Arm IK admission rejection
  ```

### 2.2 缺陷观察二：CONTRACT10-03 (FAILED Tombstone 隔离下的 WBC 污染)

- **测试用例**: `test_contract10_03_failed_isolation_propagation_to_wbc`
- **预期行为**: 当 Armature 因历史严重故障被挂起 `FAILED` 墓碑隔离时，WBC 调用 `execute_frame` 应被整体拒绝，保持场景未污染（Root 保持 `(0.0, -8.0, 0.0)`）。
- **实际行为**: WBC 顺序执行了 Base dispatch，将 `root.location` 设为 `(0.0, -6.8, 0.0)`，随后调用 Arm IK 触发隔离异常中途退出，留下了被污染的 Root 状态。
- **差异比对**:
  ```text
  AssertionError: Tuples differ: (0.0, -6.8, 0.0) != (0.0, -8.0, 0.0)
  First differing element 1:
  -6.8
  -8.0
  - (0.0, -6.8, 0.0)
  + (0.0, -8.0, 0.0)
  : CONTRACT-10 DEFECT: Root position partially modified ((0.0, -6.8, 0.0) != (0.0, -8.0, 0.0)) during FAILED isolation
  ```

### 2.3 缺陷观察三：CONTRACT10-04 (Arm IK 自身回滚成功，但 WBC 前序写入残留)

- **测试用例**: `test_contract10_04_arm_ik_rollback_vs_wbc_prior_writes_restoration`
- **预期行为**: 当 Arm IK 内部发生故障触发原子回滚时，Arm IK 自身恢复至帧前快照；但整个单帧执行失败，WBC 在此之前写入的 Root/Pelvis/Spine 也应当由 WBC 事务协调器予以恢复。
- **实际行为**: Arm IK 自身成功执行了 Layer 5 回滚（约束和 Empty 恢复），但 WBC 缺乏帧级快照或逆向补偿，导致 Root 位置停留在 `(0.0, -6.5, 0.0)`，未恢复至 `(0.0, -8.0, 0.0)`。
- **差异比对**:
  ```text
  AssertionError: Tuples differ: (0.0, -6.5, 0.0) != (0.0, -8.0, 0.0)
  First differing element 1:
  -6.5
  -8.0
  - (0.0, -6.5, 0.0)
  + (0.0, -8.0, 0.0)
  : CONTRACT-10 DEFECT: Arm IK rolled back, but WBC Root location remained corrupted ((0.0, -6.5, 0.0) != (0.0, -8.0, 0.0))
  ```

### 2.4 缺陷观察四：CONTRACT10-06 (双臂单帧执行中后手失败导致先手不对称部分提交)

- **测试用例**: `test_contract10_06_second_hand_failure_bilateral_partial_commit`
- **预期行为**: 在同一帧中，双臂作为一个协调动作整体；当 Right Hand 求解或写入失败导致回滚时，先行执行并已提交的 Left Hand 应当随同整帧回滚撤销，避免出现“左臂生效、右臂挂起”的不对称撕裂状态。
- **实际行为**: WBC 先行调用 Left hand，其事务独立提交（`influence=1.0`）；随后调用 Right hand 失败，Right hand 回滚（`influence=0.0`），整帧报错中断。Left hand 保持 `influence=1.0`，造成不可逆的半边提交。
- **差异比对**:
  ```text
  AssertionError: 1.0 != 0.0 : CONTRACT-10 DEFECT: Left hand remained committed (influence=1.0) when Right hand failed mid-frame
  ```

---

## 3. 架构根因与未来整改建议

1. **根因定位**:
   - `src/motion/whole_body_controller.py` 中的 `execute_frame()` 是一个线性命令脚本式实现：
     - Step 1: Base / Root location 写入
     - Step 2: Pelvis / Torso 旋转写入
     - Step 3: Leg IK 求解
     - Step 4: Left Hand IK 调用
     - Step 5: Right Hand IK 调用
   - 整个流程没有引入统一的 `WBCTransactionContext` 或单帧快照机制。
   - `Arm IK` 的事务边界严格局限于 `set_hand_ik_target` 内部，无法向上传播或驱动 WBC 的状态撤销。

2. **未来规划建议**:
   - 在 Task 10 之后的全身协调重构阶段，应引入顶层 `WholeBodyFrameTransaction`：
     - 在单帧派发开始前（Phase 1）捕获全身关键骨骼变换快照；
     - 双臂 Hand IK 采用嵌套事务或批量事务机制（`batch_set_hand_ik_targets`）；
     - 任一子模块（Leg/Arm/Base）抛出异常时，由顶层事务统一回退整帧变换，保证全系统的帧级原子性。
