"""Arm IK dependency graph synchronization helper migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-07)."""

from typing import Callable


def _update_arm_ik_depsgraph(
    *,
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
) -> None:
    """Synchronize the dependency graph for Arm IK calculations within mutations."""
    trigger_fault_injection("set_hand_ik_target_during_depsgraph_update")
    depsgraph_update()
