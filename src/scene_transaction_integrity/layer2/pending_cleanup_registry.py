"""Pending committed cleanup transaction registry migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L1-03)."""

from typing import Any, Dict

# [INTRODUCED 2026-11-24T13:16:00+08:00]
# NODE: 10-B / L1-03
# FUNCTION: _PENDING_ARM_RIG_CLEANUPS
# PURPOSE: 持有已逻辑提交但清理未完成的 Arm Rig 事务单一真实运行时注册表
# REASON: 将待清理事务注册表所有权从 arm_ik.py 迁入 Layer 2，消除双份字典并由 Coordinator 统一门禁引用
_PENDING_ARM_RIG_CLEANUPS: Dict[str, Any] = {}
