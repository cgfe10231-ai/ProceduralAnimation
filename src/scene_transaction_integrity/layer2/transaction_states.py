"""Transaction lifecycle and failure classification enums migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from enum import Enum


class _ArmRigTransactionState(str, Enum):
    """Explicit lifecycle state machine for Arm IK rig transactions."""
    CREATED = "CREATED"
    SNAPSHOTTING = "SNAPSHOTTING"
    ACTIVE = "ACTIVE"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    FAILED = "FAILED"


class _FailedTransactionClass(str, Enum):
    """Explicit four-class taxonomy for FAILED transactions (Task 10-B-13)."""
    FAILED_A = "FAILED-A"
    FAILED_B = "FAILED-B"
    FAILED_C = "FAILED-C"
    FAILED_D = "FAILED-D"
