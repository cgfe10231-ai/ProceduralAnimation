"""Post-commit cleanup outcome and result contracts migrated from `src/rig/arm_ik.py` (Task 10-B Layer 6)."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class _CleanupOutcome(str, Enum):
    CLEANUP_SUCCESS = "CLEANUP_SUCCESS"
    CLEANUP_INCOMPLETE = "CLEANUP_INCOMPLETE"
    CLEANUP_FAILED = "CLEANUP_FAILED"


@dataclass(frozen=True)
class _CleanupResult:
    transaction_id: str
    outcome: _CleanupOutcome
    errors: Tuple[str, ...]
    remaining_objects: int
    remaining_constraints: int
    cause: Optional[BaseException] = None
