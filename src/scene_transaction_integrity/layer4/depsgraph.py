"""Arm IK dependency graph synchronization helper migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-07)."""

from typing import Callable, Optional

import bpy


_DEPSGRAPH_UPDATER: Callable[[], None] = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None


# [INTRODUCED 2026-11-24T22:41:00+08:00]
# NODE: 10-B / L4-07
# FUNCTION: _set_test_depsgraph_updater
# PURPOSE: 在 Layer 4 唯一依赖图更新边界替换或重置测试用 Depsgraph 更新器
# REASON: 将 _DEPSGRAPH_UPDATER 状态所有权迁入 Layer 4，确保 Setter 与 Clear 操作同一份更新器并保留原有空值回退语义
def _set_test_depsgraph_updater(updater: Optional[Callable[[], None]]) -> None:
    """Private test hook to replace or wrap depsgraph update execution at the boundary."""
    global _DEPSGRAPH_UPDATER
    if updater is None:
        _DEPSGRAPH_UPDATER = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None
    else:
        _DEPSGRAPH_UPDATER = updater


# [INTRODUCED 2026-11-24T22:41:00+08:00]
# NODE: 10-B / L4-07
# FUNCTION: _clear_test_depsgraph_updater
# PURPOSE: 将 Layer 4 唯一 _DEPSGRAPH_UPDATER 重置为默认 view_layer.update() 边界
# REASON: 将测试钩子清理逻辑随更新器状态一并迁入 Layer 4，保持唯一状态所有权
def _clear_test_depsgraph_updater() -> None:
    """Clear private test depsgraph updater hook."""
    global _DEPSGRAPH_UPDATER
    _DEPSGRAPH_UPDATER = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None


# [INTRODUCED 2026-11-24T22:41:00+08:00]
# NODE: 10-B / L4-07
# FUNCTION: _depsgraph_update
# PURPOSE: 通过 Layer 4 唯一 _DEPSGRAPH_UPDATER 执行依赖图统一更新
# REASON: 将内部统一 Depsgraph 更新边界迁入 Layer 4，供各层原有回调与 arm_ik 兼容入口统一委托
def _depsgraph_update() -> None:
    """Internal unified dependency graph update boundary."""
    _DEPSGRAPH_UPDATER()


def _update_arm_ik_depsgraph(
    *,
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
) -> None:
    """Synchronize the dependency graph for Arm IK calculations within mutations."""
    trigger_fault_injection("set_hand_ik_target_during_depsgraph_update")
    depsgraph_update()
