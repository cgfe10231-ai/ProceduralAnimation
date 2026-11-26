"""Audit record registries and passive recording helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from typing import Any, Dict, List, Optional

from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _FailedTransactionClass,
)

_FAILED_A_AUDIT_RECORDS: List[Dict[str, Any]] = []

_DEISOLATION_AUDIT_LOG: List[Dict[str, Any]] = []


# [2026-11-22T16:16:30+08:00] [TASK 10-B — REGISTRY FUNCTION BATCH 1] [_record_failed_a_audit] 职责：执行 FAILED-A 被动审计记录及状态写回；解决问题：将 _FAILED_A_AUDIT_RECORDS 写入逻辑从 arm_ik.py 解耦至 Layer 2 审计注册表模块；引入必要性：经负责人与 ChatGPT 特批作为六层物理拆分中审计注册表关联函数的唯一 Layer 2 落点，不承担 FAILED 分类与协调决策。
def _record_failed_a_audit(
    session_rec: ArmatureSessionIdentityRecord,
    tx_id: str,
    f_class: _FailedTransactionClass,
    primary_exception: Optional[BaseException],
) -> Dict[str, Any]:
    """Layer 2: Record FAILED-A audit entry and terminal state without making classification decisions."""
    session_rec.isolation_state = _ArmatureIsolationState.NONE
    if session_rec.liveness_status == _ArmatureLivenessStatus.ALIVE_VERIFIED:
        session_rec.lifecycle_stage = "NORMAL_TERMINAL"
    audit_rec = {
        "transaction_id": tx_id,
        "registry_session_id": session_rec.registry_session_id,
        "failure_class": f_class.value,
        "isolation_state": _ArmatureIsolationState.NONE.value,
        "primary_exception": f"{type(primary_exception).__name__}: {primary_exception}" if primary_exception else None,
        "evidence_status": "PRE_WRITE_ZERO_MUTATION_VERIFIED",
    }
    _FAILED_A_AUDIT_RECORDS.append(audit_rec)
    return audit_rec


# [2026-11-22T16:16:30+08:00] [TASK 10-B — REGISTRY FUNCTION BATCH 1] [_append_deisolation_audit] 职责：将已形成的解除隔离或墓碑归档审计记录原样追加至 _DEISOLATION_AUDIT_LOG；解决问题：将 _DEISOLATION_AUDIT_LOG 的六处被动写入从 arm_ik.py 解耦至 Layer 2 审计注册表模块；引入必要性：经负责人与 ChatGPT 特批作为 Layer 2 被动审计写入接口，严格不做授权决策、不复制也不修改审计字典。
def _append_deisolation_audit(audit_entry: Dict[str, Any]) -> None:
    """Layer 2: Passively append an already-formed de-isolation/retirement audit entry."""
    _DEISOLATION_AUDIT_LOG.append(audit_entry)
