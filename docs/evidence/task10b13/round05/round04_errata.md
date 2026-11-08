# 10-B-13 · 第四轮审计材料勘误（不覆盖历史证据）

基线：`629a47eefef3986473c770bfa0cd630cfe44c143`。

1. 实际持久化隔离字典为 `_ISOLATED_FAILED_ARMATURES`；旧材料引用的 `_DEAD_ARMATURE_TOMBSTONES`、`_ACTIVE_ARMATURE_TRANSACTIONS`、`VerificationEvidence`、`RECOVERY_UNCERTAIN_REJECTED` 并非本基线中的实际符号。
2. `verify_armature_deisolation_evidence(arm=None, session_id=None)` 返回 `dict`，真实键为 `can_deisolate`、`status`、`case`、`reasons`；可信快照来自 `snapshot_reference` 和 `snapshot_trusted`。
3. 关系恢复不确定性存储于 `prepared_relationship_mutations[*]["operation_state"] == _RelationshipOperationState.RECOVERY_UNCERTAIN`，不是 `recovery_state`。
4. 原 TEST-151 缺少可信快照，先命中 Case 2，不能证明 Case 1 / Condition 6；第五轮将其改为真实可达的 Case 1 分支并增加严格断言。
5. 对象存在性的 UNKNOWN 不足以立死亡墓碑；但真实对象存在且原 Armature DataBlock 被证实替换/失效，仍须保留 FAILED-D 路径。失效类型必须通过真实身份核验认定。
6. `_clear_or_retire_failure_isolation_by_coordinator` 原实现已有注册表 Grant ID、session、action、tx、failure class、isolation state 与一次性消费检查；旧报告将备用参数直接等同于完全越权并不准确。本轮删除参数语义歧义，但不凭空加入 300 秒 TTL。
7. 原第四轮指纹结论忽略 `_freeze_fingerprint_property_value` 对不支持类型的原样返回、失效 RNA 降为 None、`_has_nan_or_inf` 迭代异常吞没等缺口；第五轮已安排 fail-closed 修复及独立覆盖。
8. 多 Armature 的会话门禁隔离不能误写成多 Rig 独立 Reset 支持：当前业务 API 使用全局 HandIK/ElbowPole 名称，未修改命名空间架构。
9. Round4 `fault_reproduction.md` 中不匹配真实源码的伪代码不构成可执行重现证据。优先采用第五轮真实 Blender 测试输出。

本勘误不声称第四轮历史材料已原地修复；保留可追溯审计差异。
