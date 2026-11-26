"""Six-layer Scene Transaction Integrity package public boundary (Task 10-B)."""

import src.rig.arm_ik as _arm_ik_domain  # noqa: F401
from src.scene_transaction_integrity import (
    fault_injection,
    layer2,
    layer3,
    layer5,
    layer6,
    layer1,
    layer4,
    wiring,
)
from src.scene_transaction_integrity.layer1 import (
    ensure_armature_session_identity,
    query_admission_gate_status,
    retry_pending_arm_rig_cleanup,
)
from src.scene_transaction_integrity.layer2 import (
    ArmatureSessionIdentityRecord,
    _ACTIVE_TRANSACTION_STACK,
    _ArmRigTransactionContext,
    get_pending_arm_rig_cleanup_ids,
)
from src.scene_transaction_integrity.layer3 import (
    ExternalControllerNameConflictError,
    _require_existing_arm_ik_controller_ownership,
)
from src.scene_transaction_integrity.wiring import (
    _arm_rig_transaction,
    request_armature_deisolation,
    retire_dead_armature_tombstone,
    verify_armature_deisolation_evidence,
)

__all__ = (
    "ArmatureSessionIdentityRecord",
    "ExternalControllerNameConflictError",
    "_ACTIVE_TRANSACTION_STACK",
    "_ArmRigTransactionContext",
    "_arm_rig_transaction",
    "_require_existing_arm_ik_controller_ownership",
    "ensure_armature_session_identity",
    "fault_injection",
    "get_pending_arm_rig_cleanup_ids",
    "layer1",
    "layer2",
    "layer3",
    "layer4",
    "layer5",
    "layer6",
    "query_admission_gate_status",
    "request_armature_deisolation",
    "retire_dead_armature_tombstone",
    "retry_pending_arm_rig_cleanup",
    "verify_armature_deisolation_evidence",
    "wiring",
)
