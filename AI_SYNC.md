# AI_SYNC：跨 AI 状态同步与当前工程交接卡片

* **项目**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **文档审查起点 HEAD**：`7547c91a31f0b97a19de335ad5c61cc617b017a2`
* **最近一次生产源码核验基准**：`2904857433af01c2a7991e2da085b3c0f53a145f`
* **当前分支**：`master`
* **当前任务**：PKG-5 / 09-B-4 — Lower-Limb World Rotation & Effective Parent Transform Re-verification
* **当前状态**：`IN PROGRESS — NOT ACCEPTED`
* **当前结论**：修复尚未完成，仍存在未解决问题。不得把历史 09-B 的验收记录当作 09-B-3 的验收结果。

---

## 1. 当前阶段与准入边界

当前正在处理 PKG-5 / 09-B-4。

后续节点顺序：

1. 09-B-4：Lower-Limb World Rotation / 有效父级变换域 / 控制器状态完整性与失败原子性。
2. 10：Upper-Limb IK/FK。
3. 11：FootLock。
4. 12：PKG-5 综合接口闭环与全仓联合验收。

09-B-3、10、11、12 完成联合验收，并获得项目负责人明确批准之前，不得开启 Phase 7B。

Phase 7B 的当前权威定义为：

`Upper-Limb Independent Motion & End-Effector Target Verification`

Phase 7C 才是 Pipeline A 与 Pipeline B 的未来合流阶段。不得把未来合流提前列为当前 09-B-3 的修复要求。

---

## 2. 09-B-3 当前生产源码事实

生产源码：

- `src/rig/ik.py`
- `tests/test_leg_ik_world_rotation_contract.py`

有效父级矩阵：

\[
M_{\mathrm{eff}} =
M_{\mathrm{parent}}
M_{\mathrm{parent\_inverse}}
\]

当前 `_validate_effective_parent_transform()` 的实际支持域：

1. 16 个矩阵元素必须全部有限。
2. 仿射矩阵最后一行必须满足容差 `1e-6`。
3. `det(A) < 0`：拒绝镜像反射。
4. `det(A) == 0`：拒绝奇异矩阵。
5. `s_sq <= 1e-12`：拒绝退化尺度。
6. Gram 矩阵相对偏差大于 `1e-6`：拒绝非共形变换。
7. 支持纯旋转，以及正均匀缩放与旋转的组合。

必须注意：

- 不得将行列式阈值描述成 `det > 1e-7`。
- 不得将共形偏差阈值描述成 `1e-4`。
- 当前实现并不是简单地以 `det <= 1e-7` 拒绝所有变换。
- TEST-18 已经构造正均匀缩放 `0.001`，其行列式为 `1e-9`，并验证这种变换应被接受。

---

## 3. 当前测试状态与证据边界

当前测试文件包含 TEST-01 至 TEST-21。

现有历史执行记录：

- 旧交接记录证明此前曾执行 17 项测试并获得 17/17 PASS。
- 该记录早于 TEST-18 至 TEST-21 的增加。
- 当前仓库没有提供 TEST-18 至 TEST-21 的实际执行证据。
- 当前不得宣称 21/21 PASS。
- 当前不得宣称 09-B-3 已经修复完成。

### 已发现的测试断言覆盖缺口

`tests/test_leg_ik_world_rotation_contract.py` 中：

- `_capture_rig_state()` 保存了部分控制器旋转通道、`matrix_parent_inverse`、骨骼 `matrix_basis` 等字段。
- `_assert_rig_state_identical()` 没有逐项比较全部已保存字段。
- 当前断言主要比较控制器 `matrix_world`、`location`、`scale`、`parent`、`is_locked`，以及骨骼 `matrix`、`location`、`scale`。
- 控制器旋转通道、`rotation_mode`、`matrix_parent_inverse`，以及骨骼 `matrix_basis` 等已保存字段没有被完整逐项断言。

因此，TEST-17 目前不能作为“所有已保存状态通道均已验证完整恢复”的充分证据。

这是已发现的测试证据缺口，不代表已经证明生产回滚实现必然错误。

### 另一个源码注释问题

测试文件顶部 TEST-15 的说明仍写着 `det <= 1e-7`，与当前生产校验的 `det == 0` 奇异矩阵判定不一致。

本次任务是文档修订，不得擅自修改测试源码。该源码注释问题应保留为后续测试修订事项。

---

## 4. Finding 状态边界

- `FIND-R3-01`：历史原 09-B 修复与历史验收记录继续有效，历史状态为 `RESOLVED / FIXED / VERIFIED`。
- 当前 09-B-3：是在历史修复基础上的后续独立修复节点，仍为 `IN PROGRESS — NOT ACCEPTED`。
- `FIND-R3-03`：当前未关闭，归属 PKG-5 / 11 FootLock。
- `FIND-R3-04`：当前未关闭，归属 PKG-5 / 11 FootLock。

不得把 FIND-R3-01 的历史关闭状态与当前 09-B-3 的完成状态混为一谈。

---

## 5. 当前下一步

当前唯一优先事项仍是完成 09-B-3 修复与独立核验。

不得提前开始 10，不得提前进入 11 或 12，不得开启 Phase 7B。

本文件中的历史测试结果仅代表对应历史执行现场，不得复制为当前提交的执行结果。

---

## 6. 文档维护纪律

- `ARCHITECTURE.md` 是全项目总架构保护文件。
- `ARCHITECTURE_SYNC.md` 是当前工程动态架构文档。
- `PROJECT_STATE.md` 是当前真实工程状态总看板。
- `HANDOFF.md` 是跨会话交接文档。
- `AI_SYNC.md` 是跨 AI 当前任务状态卡。
- `OPEN_FINDINGS.md` 是当前问题登记权威表。
- `DECISIONS.md` 保留正式历史决策。
- `CHANGELOG.md` 只追加新的历史记录，不改写旧记录。
- 历史审计报告与证据文件不得改写其历史事实。

任何任务开始前，必须读取当前状态文件并核对真实 Git HEAD。不得根据旧会话中的状态继续执行。
