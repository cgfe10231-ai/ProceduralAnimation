"""Managed Armature session identity and FAILED isolation registries migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.scene_transaction_integrity.layer2 import (
    audit_registries as _audit_registries,
    identity_helpers as _identity_helpers,
)
from src.scene_transaction_integrity.layer2.relationship_states import (
    _RelationshipOperationState,
)
from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _FailedTransactionClass,
)

_MANAGED_ARMATURE_IDENTITIES: Dict[str, ArmatureSessionIdentityRecord] = {}
_ISOLATED_FAILED_ARMATURES: Dict[str, Dict[str, Any]] = {}


# [INTRODUCED 2026-11-25T00:02:00+08:00]
# NODE: 10-B / L2-13
# FUNCTION: _record_armature_failure_isolation_by_coordinator
# PURPOSE: 接收 Coordinator 已确定的失败分类并登记原有隔离状态、墓碑及恢复证据
# REASON: 将正常准入阶段首次触发、后续异常阶段共享的隔离记录主节点迁入 Layer 2
def _record_armature_failure_isolation_by_coordinator(
    session_rec: ArmatureSessionIdentityRecord,
    tx: Any,
    failure_class: Any,
    primary_exception: Optional[BaseException],
    secondary_exception: Optional[BaseException] = None,
    evidence_status: str = "SNAPSHOT_AVAILABLE",
    missing_evidence_reasons: Optional[List[str]] = None,
    *,
    failed_transaction_class_cls: Any = _FailedTransactionClass,
    armature_isolation_state_cls: Any = _ArmatureIsolationState,
    armature_liveness_status_cls: Any = _ArmatureLivenessStatus,
    relationship_operation_state_cls: Any = _RelationshipOperationState,
    isolated_failed_armatures: Optional[Dict[str, Dict[str, Any]]] = None,
    record_failed_a_audit: Optional[Callable[..., Dict[str, Any]]] = None,
    check_original_object_liveness: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Layer 2: Record FAILED-B / FAILED-C / FAILED-D isolation or tombstone under Layer 1 Coordinator authority."""
    if isolated_failed_armatures is None:
        isolated_failed_armatures = _ISOLATED_FAILED_ARMATURES
    if record_failed_a_audit is None:
        record_failed_a_audit = _audit_registries._record_failed_a_audit
    if check_original_object_liveness is None:
        check_original_object_liveness = _identity_helpers._check_original_object_liveness
    f_class = (
        failure_class
        if isinstance(failure_class, failed_transaction_class_cls)
        else failed_transaction_class_cls(failure_class)
    )
    tx.failure_class = f_class.value

    if f_class == failed_transaction_class_cls.FAILED_A:
        return record_failed_a_audit(
            session_rec=session_rec,
            tx_id=tx.tx_id,
            f_class=f_class,
            primary_exception=primary_exception,
        )

    if f_class == failed_transaction_class_cls.FAILED_B:
        iso_state = armature_isolation_state_cls.ISOLATED_FAILED_B
    elif f_class == failed_transaction_class_cls.FAILED_C:
        iso_state = armature_isolation_state_cls.ISOLATED_FAILED_C
    elif f_class == failed_transaction_class_cls.FAILED_D:
        iso_state = armature_isolation_state_cls.TOMBSTONED_FAILED_D
    else:
        raise RuntimeError(f"Unsupported failure class for isolation: {f_class}")

    session_rec.isolation_state = iso_state
    if f_class == failed_transaction_class_cls.FAILED_D:
        session_rec.liveness_status = armature_liveness_status_cls.INVALIDATED_DEAD
        obj_liveness = check_original_object_liveness(session_rec)
        if obj_liveness["status"] == "ALIVE":
            session_rec.in_live_blender_collection = True
        elif obj_liveness["status"] == "ABSENT":
            session_rec.in_live_blender_collection = False
        session_rec.lifecycle_stage = "TOMBSTONED_FAILED_D"

    snapshot_trusted = bool(
        tx.snapshot is not None
        and f_class in (failed_transaction_class_cls.FAILED_B, failed_transaction_class_cls.FAILED_C)
        and evidence_status != "RECOVERY_EVIDENCE_INSUFFICIENT"
    )

    uncertain_ops = [
        {
            "operation_id": r.get("operation_id"),
            "intended_mutation": r.get("intended_mutation"),
            "operation_state": (
                r.get("operation_state").value
                if isinstance(r.get("operation_state"), Enum)
                else str(r.get("operation_state"))
            ),
        }
        for r in getattr(tx, "prepared_relationship_mutations", [])
        if r.get("operation_state") == relationship_operation_state_cls.RECOVERY_UNCERTAIN
    ]

    tombstone_rec: Optional[Dict[str, Any]] = None
    if f_class == failed_transaction_class_cls.FAILED_D:
        tombstone_rec = {
            "registry_session_id": session_rec.registry_session_id,
            "transaction_id": tx.tx_id,
            "registration_pointer": session_rec.registration_pointer,
            "original_data_pointer": session_rec.original_data_pointer,
            "registered_name_snapshot": session_rec.registered_name_snapshot,
            "failure_class": f_class.value,
            "isolation_state": iso_state.value,
            "retirement_state": "ACTIVE_TOMBSTONE",
            "created_controller_objects": list(getattr(tx, "created_controller_objects", [])),
            "created_collections": list(getattr(tx, "created_collections", [])),
            "primary_exception": f"{type(primary_exception).__name__}: {primary_exception}" if primary_exception else None,
            "secondary_exception": f"{type(secondary_exception).__name__}: {secondary_exception}" if secondary_exception else None,
        }
        session_rec.tombstone_record = tombstone_rec

    iso_record: Dict[str, Any] = {
        "registry_session_id": session_rec.registry_session_id,
        "transaction_id": tx.tx_id,
        "failure_class": f_class.value,
        "isolation_state": iso_state.value,
        "liveness_status": session_rec.liveness_status.value,
        "registration_pointer": session_rec.registration_pointer,
        "original_data_pointer": session_rec.original_data_pointer,
        "registered_name_snapshot": session_rec.registered_name_snapshot,
        "primary_exception": (
            f"{type(primary_exception).__name__}: {primary_exception}"
            if primary_exception is not None
            else None
        ),
        "secondary_exception": (
            f"{type(secondary_exception).__name__}: {secondary_exception}"
            if secondary_exception is not None
            else None
        ),
        "snapshot_reference": tx.snapshot if snapshot_trusted else None,
        "snapshot_trusted": snapshot_trusted,
        "evidence_status": evidence_status,
        "missing_evidence_reasons": list(missing_evidence_reasons or []),
        "transaction_context": tx,
        "created_controller_objects": list(getattr(tx, "created_controller_objects", [])),
        "created_constraints": list(getattr(tx, "created_constraints", [])),
        "created_collections": list(getattr(tx, "created_collections", [])),
        "prepared_relationship_mutations": list(getattr(tx, "prepared_relationship_mutations", [])),
        "recovery_uncertain_operations": uncertain_ops,
        "tombstone_record": tombstone_rec,
    }
    isolated_failed_armatures[session_rec.registry_session_id] = iso_record
    tx.isolation_record = iso_record
    return iso_record
