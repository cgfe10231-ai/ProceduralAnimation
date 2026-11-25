"""Constraint target/subtarget pair state classification migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-08)."""

from typing import Any, Callable, Optional

import bpy

from src.scene_transaction_integrity.layer2.relationship_states import (
    _RelationshipOperationState,
)
from src.scene_transaction_integrity.layer3.resource_contracts import (
    _find_live_object_by_identity,
)


# [INTRODUCED 2026-11-23T23:07:30+08:00]
# NODE: 10-B / L3-08
# FUNCTION: _classify_constraint_target_pair_effect
# PURPOSE: Conservatively classify two-field Constraint Target/Subtarget RNA state after interrupted writes based on original and destination Object/Subtarget identities
# REASON: Migrate relationship state classification shared by normal target writes and Rollback from src/rig/arm_ik.py into Layer 3 while preserving partial-write reversibility
def _classify_constraint_target_pair_effect(
    current_target: Optional[bpy.types.Object],
    current_subtarget: str,
    orig_target: Optional[bpy.types.Object],
    orig_target_ptr: Optional[int],
    orig_subtarget: str,
    dest_target: Optional[bpy.types.Object],
    dest_target_ptr: Optional[int],
    dest_subtarget: str,
    *,
    relationship_operation_state_cls: Any = _RelationshipOperationState,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ] = _find_live_object_by_identity,
) -> Any:
    """Classify two-field RNA state conservatively after interrupted target writes.

    NO_EFFECT is allowed ONLY for an exact original target AND subtarget pair.
    A recognized partial or complete write must stay reversible (APPLIED_VERIFIED).
    A third-party value or unreadable identity is RECOVERY_UNCERTAIN.
    """
    def matches_target(ref: Any, expected: Any, expected_ptr: Optional[int]) -> bool:
        if expected is None:
            return ref is None and expected_ptr is None
        if ref is None or expected_ptr is None:
            return False
        try:
            return (
                ref == expected
                and int(ref.as_pointer()) == expected_ptr
                and find_live_object_by_identity(expected, expected_ptr) is not None
            )
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            return False

    is_orig_target = matches_target(current_target, orig_target, orig_target_ptr)
    is_dest_target = matches_target(current_target, dest_target, dest_target_ptr)
    is_orig_sub = current_subtarget == orig_subtarget
    is_dest_sub = current_subtarget == dest_subtarget

    if is_orig_target and is_orig_sub:
        return relationship_operation_state_cls.NO_EFFECT
    if (is_orig_target or is_dest_target) and (is_orig_sub or is_dest_sub):
        return relationship_operation_state_cls.APPLIED_VERIFIED
    return relationship_operation_state_cls.RECOVERY_UNCERTAIN
