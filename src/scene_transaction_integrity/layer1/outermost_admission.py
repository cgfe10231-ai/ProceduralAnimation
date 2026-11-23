"""Outermost Arm Rig transaction admission coordinator migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-01)."""

from typing import Any, Callable, Dict, Tuple


# [INTRODUCED 2026-11-24T00:37:30+08:00]
# NODE: 10-B / L1-01
# FUNCTION: _admit_outermost_arm_rig_transaction
# PURPOSE: 按原始顺序协调外层 Arm Rig 事务的 Session 建立、Cleanup Gate、FAILED Gate 和身份验证调用
# REASON: 将正常外层事务准入调用迁入 Layer 1，同时保留原协调器的失败分支和最终事务控制权
def _admit_outermost_arm_rig_transaction(
    arm: Any,
    *,
    ensure_armature_session_identity: Callable[[Any], Any],
    assert_arm_rig_cleanup_gate: Callable[[Any, Any], None],
    assert_arm_rig_failed_isolation_gate: Callable[[Any, Any], None],
    verify_armature_session_identity_record: Callable[..., Dict[str, Any]],
) -> Tuple[Any, Dict[str, Any]]:
    """Execute outermost transaction admission gates and session identity verification in original order."""
    session_rec = ensure_armature_session_identity(arm)

    # Gate 1: Reject a new outermost transaction when previous committed cleanup is unresolved
    assert_arm_rig_cleanup_gate(arm, session_rec)

    # Gate 2: Reject a new outermost transaction when Armature session is isolated due to FAILED
    assert_arm_rig_failed_isolation_gate(arm, session_rec)

    # Gate 3: Verify 7-condition Armature Session Identity
    admission_id_check = verify_armature_session_identity_record(session_rec, candidate_arm=arm)
    return session_rec, admission_id_check
