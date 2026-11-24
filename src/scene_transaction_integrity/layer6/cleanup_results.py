"""Post-commit cleanup outcome and result contracts migrated from `src/rig/arm_ik.py` (Task 10-B Layer 6)."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Tuple


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


# [INTRODUCED 2026-11-24T13:44:00+08:00]
# NODE: 10-B / L1-06
# FUNCTION: _build_cleanup_result
# PURPOSE: 统计残余暂存资源与错误列表、判定 CLEANUP_SUCCESS/INCOMPLETE/FAILED、写入 cleanup_error 并构造不可变 _CleanupResult
# REASON: 将清理结果计算与结果对象构造迁入 Layer 6 现有 cleanup_results 模块，同时保持原枚举、dataclass 及无生命周期写权限边界
def _build_cleanup_result(
    tx: Any,
    cleanup_failures: List[str],
    first_cause: Optional[BaseException],
    *,
    cleanup_outcome_cls: Any,
    cleanup_result_cls: Any,
) -> Any:
    """Build the original cleanup result from execution evidence."""
    rem_objs = len(tx.uncleaned_stashed_objects)
    rem_cons = len(tx.uncleaned_stashed_constraints)
    err_tuple = tuple(cleanup_failures)

    if not err_tuple and rem_objs == 0 and rem_cons == 0:
        outcome = cleanup_outcome_cls.CLEANUP_SUCCESS
        tx.cleanup_error = None
    elif rem_objs > 0 or rem_cons > 0:
        outcome = cleanup_outcome_cls.CLEANUP_INCOMPLETE
        tx.cleanup_error = (
            "; ".join(err_tuple)
            if err_tuple
            else "Cleanup incomplete: remaining stashed resources"
        )
    else:
        outcome = cleanup_outcome_cls.CLEANUP_FAILED
        tx.cleanup_error = (
            "; ".join(err_tuple)
            if err_tuple
            else "Cleanup result unprovable or failed"
        )

    return cleanup_result_cls(
        transaction_id=tx.tx_id,
        outcome=outcome,
        errors=err_tuple,
        remaining_objects=rem_objs,
        remaining_constraints=rem_cons,
        cause=first_cause,
    )
