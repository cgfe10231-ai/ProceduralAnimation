# PKG-5 / Task 10-B-1-FIX-01: Arm IK 自动初始化前置变换预检与零副作用修复报告

> **任务标识**: PKG-5 / Task 10-B-1-FIX-01 (Arm IK 自动初始化前置变换预检与零副作用修复)
>
> **前置基线 Commit**: `7d9b0e0b9292dab86da04e653c39ce777876f648`
>
> **执行日期**: 2026-11-03
>
> **环境**: Windows 11 / Blender 5.1.1 / Python 3.11.9
>
> **任务性质**: 已有接口合同缺陷修复 (Interface Defect Fix)
>
> **交付状态**: `10-B-1-FIX-01 IMPLEMENTED — TESTED — ARCHIVED` (整体 10-B-1 保持 `PENDING INDEPENDENT AUDIT`)

---

## 1. 原始缺陷根因

在修复前，`set_hand_ik_target()` 在发现 `HandIK` 或 `ElbowPole` 控制器缺失时，会在第一时间调用：
```python
setup_arm_ik(arm, initial_influence=valid_influence)
```
`setup_arm_ik()` 会对场景产生实质性写入：
1. 在 `Character` 集合中创建 4 个 Empty 控制器对象；
2. 为左右两臂骨骼添加 `IK` 约束和 `COPY_ROTATION` 约束；
3. 修改 PoseBone 的 `ik_min`/`ik_max` 限制属性和 Pre-bend Hint；
4. 强制刷新场景依赖图。

而对于父级变换有效性矩阵（Effective Parent Matrix，`M_eff = M_parent @ matrix_parent_inverse`）的数学合法性校验（是否仿射、非奇异、非反射、共形无剪切且尺度非退化）发生在上述调用之后。当父级对象（如 `arm.parent` 或 `CharacterRoot`）存在非共形变换（如非均匀缩放）或镜像反射时，函数会在已经对场景造成永久修改后抛出 `ValueError`。这构成了明确的**零副作用合同违反**（Zero-Side-Effect Contract Violation）。

---

## 2. 修复前后执行顺序对比

### 2.1 修复前执行顺序
1. **Phase A（参数校验）**: 用户输入参数类型与范围校验；
2. **控制器存在性检查与初始化**: 若缺失控制器，**立即调用 `setup_arm_ik()`**（产生场景修改）；
3. **依赖图同步**: `bpy.context.view_layer.update()`；
4. **有效父级变换校验**: `validate_effective_parent_transform()`（**若失败抛出异常，场景已被污染**）；
5. **Phase D（目标反解与提交）**: 目标计算与场景提交。

### 2.2 修复后执行顺序
1. **Phase A（用户输入预验证）**:
   * 严格保留全部参数校验：`_validate_side()`, `_validate_vec3(world_xyz)`, `_validate_vec3(hand_rotation_deg)`, `_validate_vec3(pole_world_xyz)`, `_validate_bool(clamp_reach)`, `_validate_influence(influence)`。
2. **Phase B（无场景写入的控制器与环境预检）**:
   * 解析骨架，执行 `bpy.context.view_layer.update()` 保证矩阵读取自最新依赖图；
   * 查询当前控制器是否存在，并识别是否需要触发 `setup_arm_ik()`；
   * 对于已存在的控制器，调用 `compute_effective_parent_matrix(obj)` 获得实际有效父级矩阵；
   * 对于尚未存在的控制器，依据 `setup_arm_ik()` 真实规则计算其预期有效父级矩阵：
     $$M_{\text{eff}} = M_{\text{parent}} \cdot I_4$$
     （若不存在父级则使用单位矩阵 $I_4$）；
   * 对实际存在和即将创建的所有控制器逐一调用 `validate_effective_parent_transform()` 完成数学支持域验证；
   * **所有控制器检查全部通过后，才允许进入 Phase C**。
3. **Phase C（自动初始化）**:
   * 仅在 Phase B 全部校验通过且确实缺失控制器时，调用现有 `setup_arm_ik(arm, initial_influence=valid_influence)`；
   * 获取初始化后的控制器对象引用；
   * 使用 Phase B 已经验证的有效父级矩阵进行后续坐标反解。
4. **Phase D（目标计算与提交）**:
   * 保留原有 Shoulder 计算、Reach Clamping、Pole Target、Hand Rotation 四元数反解；
   * 校验派生坐标与四元数有限性；
   * 提交控制器位置/旋转，更新约束 Influence。

---

## 3. 具体生产代码修改位置

* **文件**: [`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py)
* **修改范围**:
  1. 新增私有预检辅助函数 `_preflight_arm_ik_parent_transforms(arm, valid_side, root_obj)`：纯只读检查，计算并校验已存在及待创建控制器的有效父级矩阵，返回 `(needs_auto_init, eff_ik_mat, eff_pole_mat)`。
  2. 重构 `set_hand_ik_target()` 内部执行流：严格执行 Phase A $\to$ Phase B $\to$ Phase C $\to$ Phase D 顺序，杜绝在 Phase B 验证完成前产生任何场景写入。

---

## 4. 专项测试结果（TEST-25 至 TEST-27）

在 [`tests/test_task10b_input_validation.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_input_validation.py) 中新增 3 项自动化专项测试：

| 测试 ID | 测试方法 | 测试场景与断言 | 结果 |
|:---|:---|:---|:---:|
| **TEST-25** | `test_25_auto_init_invalid_parent_has_zero_scene_mutation` | 未初始化状态下，初始化父级 Scale 设为非共形 `(1.0, 2.0, 1.0)`。调用 `set_hand_ik_target` 抛出 `ValueError`。调用前后捕获完整场景深度快照（对象、集合、PoseBone 变换/IK限制/约束配置），快照逐项相等证明 100% 零场景突变，无 Empty 或约束生成。 | **PASS** |
| **TEST-26** | `test_26_partial_init_invalid_new_parent_has_zero_scene_mutation` | 部分初始化状态下（仅手动创建合法的 `HandIK.L`，其余 3 个缺失），初始化父级 Scale 设为反射 `(-1.0, 1.0, 1.0)`。调用 L 侧 `set_hand_ik_target` 抛出 `ValueError`。深度快照证明已有 `HandIK.L` 保持未变，缺失的 `ElbowPole.L` 及其他控制器与约束均未创建。 | **PASS** |
| **TEST-27** | `test_27_valid_parent_first_time_auto_init_succeeds` | 合法父级下，首次调用 `set_hand_ik_target` 正常触发自动初始化。验证 4 个控制器正确创建，左右两侧约束建立，手部目标位置/朝向/权重正确赋予，返回值与场景真实状态一致。 | **PASS** |

* **专项测试整体执行结果**:
  * 命令: `& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" -b -P tests/test_task10b_input_validation.py`
  * 结果: **Ran 27 tests in 2.305s — OK (27/27 PASS, 退出码 0)**

---

## 5. 10-A 回归测试结果

* **命令**: `& "C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe" tests/run_test_suite.py --test-id arm_ik_lifecycle_world_transform_contract`
* **测试文件**: `tests/test_arm_ik_lifecycle_world_transform_contract.py`
* **结果**: **Ran 30 tests in 5.66s — OK (30/30 PASS, 退出码 0)**

---

## 6. 四级分层回归矩阵

通过 `python tests/run_test_suite.py --tier <tier>` 逐级全量回归：

| Tier | 套件数 | 计划执行 | 实际执行 | 普通 PASS | AUTOMATED_PASS | FAIL | ERROR | 退出码 | 执行耗时 |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Quick** | 19 | 19 | 19 | 16 | 3 | 0 | 0 | **0** | 50.44s |
| **Physics** | 27 | 27 | 27 | 24 | 3 | 0 | 0 | **0** | 109.13s |
| **Motion** | 12 | 12 | 12 | 6 | 6 | 0 | 0 | **0** | 48.60s |
| **Full** | 42 | 42 | 42 | 33 | 9 | 0 | 0 | **0** | 156.51s |

> **注**: `AUTOMATED_PASS` 仅标定自动化断言通过，GUI 视觉验收继续遵循既定计划推迟。

---

## 7. 文档与符号物理存在审计

* **命令**: `python tests/audit_c2_final_inspector.py --verify-docs`
* **输出**:
  ```text
  [SELF-TEST] PASS: All 6 validator test cases (Positive, Negative, Proposed, Prose, Dynamic, Clause Exemption) verified successfully.
  [VERIFY-DOCS] PASS: All referenced src/tests paths exist on disk and zero phantom symbols found.
  ```
* **退出码**: `0`

---

## 8. 未解决事项与后续执行边界

1. 本任务仅针对自动初始化前置变换预检缺陷进行了单一职责修复，交付标识为 `10-B-1-FIX-01`。
2. 整体 `Task 10-B-1` 状态保持 `PENDING INDEPENDENT AUDIT`，不擅自声称已获得最终验收。
3. 通用事务快照与回滚系统属于既定的 `Task 10-B-2`，未提前混入本任务。
4. 严禁进入 `Task 10-C` 或其他后续任务，等待独立审计与下一阶段指令。
