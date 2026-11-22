"""Relationship operation state machine and legal transition table migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from enum import Enum
from typing import Dict, Tuple


class _RelationshipOperationState(str, Enum):
    """Explicit 7-state machine for relationship mutation log entries (Task 10-B-11)."""
    PREPARED = "PREPARED"
    APPLYING = "APPLYING"
    APPLIED_VERIFIED = "APPLIED_VERIFIED"
    CONFIRMED = "CONFIRMED"
    NO_EFFECT = "NO_EFFECT"
    REVERTED = "REVERTED"
    RECOVERY_UNCERTAIN = "RECOVERY_UNCERTAIN"


_LEGAL_RELATIONSHIP_LOG_TRANSITIONS: Dict[
    Tuple[_RelationshipOperationState, _RelationshipOperationState], str
] = {
    (_RelationshipOperationState.PREPARED, _RelationshipOperationState.NO_EFFECT): "PREPARED -> NO_EFFECT",
    (_RelationshipOperationState.PREPARED, _RelationshipOperationState.APPLYING): "PREPARED -> APPLYING",
    (_RelationshipOperationState.APPLYING, _RelationshipOperationState.APPLIED_VERIFIED): "APPLYING -> APPLIED_VERIFIED",
    (_RelationshipOperationState.APPLYING, _RelationshipOperationState.NO_EFFECT): "APPLYING -> NO_EFFECT",
    (_RelationshipOperationState.APPLYING, _RelationshipOperationState.RECOVERY_UNCERTAIN): "APPLYING -> RECOVERY_UNCERTAIN",
    (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.CONFIRMED): "APPLIED_VERIFIED -> CONFIRMED",
    (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.REVERTED): "APPLIED_VERIFIED -> REVERTED",
    (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.RECOVERY_UNCERTAIN): "APPLIED_VERIFIED -> RECOVERY_UNCERTAIN",
    (_RelationshipOperationState.CONFIRMED, _RelationshipOperationState.REVERTED): "CONFIRMED -> REVERTED",
    (_RelationshipOperationState.CONFIRMED, _RelationshipOperationState.RECOVERY_UNCERTAIN): "CONFIRMED -> RECOVERY_UNCERTAIN",
}
