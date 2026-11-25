"""Shared test fault injection boundary migrated from `src/rig/arm_ik.py` (Task 10-B)."""

from typing import Any, Callable, Dict, Optional


_FAULT_INJECTION_HOOK: Optional[Callable[[str, Dict[str, Any]], None]] = None


# [INTRODUCED 2026-11-25T17:56:00+08:00]
# NODE: 10-B
# FUNCTION: _set_test_fault_injection_hook
# PURPOSE: 在共享故障注入边界唯一设置私有测试故障注入回调对象
# REASON: 将 _FAULT_INJECTION_HOOK 及 Setter 从 arm_ik.py 物理迁入独立的 shared fault_injection 模块
def _set_test_fault_injection_hook(hook: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
    """Private test hook callback for deterministic fault injection during tests."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = hook


# [INTRODUCED 2026-11-25T17:56:00+08:00]
# NODE: 10-B
# FUNCTION: _clear_test_fault_injection_hook
# PURPOSE: 将共享故障注入边界唯一的私有测试钩子重设为 None
# REASON: 与 _FAULT_INJECTION_HOOK 一并迁入 shared fault_injection 模块，确保 Setter/Clear/Trigger 操作同一状态
def _clear_test_fault_injection_hook() -> None:
    """Clear private internal test fault injection hook."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = None


# [INTRODUCED 2026-11-25T17:56:00+08:00]
# NODE: 10-B
# FUNCTION: _trigger_fault_injection
# PURPOSE: 在钩子激活时按原语义与异常处理行为向当前 _FAULT_INJECTION_HOOK 触发故障注入阶段与上下文
# REASON: 将共享故障注入触发入口迁入 shared fault_injection 模块，并经 arm_ik.py 兼容代理保持原有回调接线
def _trigger_fault_injection(stage: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Trigger internal fault injection if a hook is active."""
    global _FAULT_INJECTION_HOOK
    if _FAULT_INJECTION_HOOK is not None:
        _FAULT_INJECTION_HOOK(stage, context or {})
