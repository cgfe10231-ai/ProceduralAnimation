"""Arm Rig Transaction Context state initializer migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-04)."""

import uuid
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

import bpy

from src.scene_transaction_integrity.layer2.identity_helpers import _safe_object_pointer
from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)


# [INTRODUCED 2026-11-23T17:30:42+08:00]
# NODE: 10-B / L2-04
# FUNCTION: _initialize_arm_rig_transaction_context
# PURPOSE: Initialize all 35 instance attributes, containers, CREATED state, and 4 independent receipt seals of _ArmRigTransactionContext in Layer 2
# REASON: Authorized L2-04 migration of _ArmRigTransactionContext.__init__ body while keeping class identity in arm_ik.py and avoiding reverse imports via explicit ensure_armature_session_identity callback
def _initialize_arm_rig_transaction_context(
    self: Any,
    arm: bpy.types.Object,
    session_record: Optional[ArmatureSessionIdentityRecord] = None,
    *,
    ensure_armature_session_identity: Callable[[bpy.types.Object], ArmatureSessionIdentityRecord],
) -> None:
    self.arm = arm
    if session_record is None and arm is not None:
        try:
            session_record = ensure_armature_session_identity(arm)
        except BaseException:
            session_record = None
    self.session_record: Optional[ArmatureSessionIdentityRecord] = session_record
    self.session_id: Optional[str] = (
        session_record.registry_session_id
        if session_record is not None
        else None
    )
    self.arm_ptr = _safe_object_pointer(
        arm,
        fallback=(session_record.registration_pointer if session_record is not None else 0),
    )
    self.state: _ArmRigTransactionState = _ArmRigTransactionState.CREATED
    self.snapshot: Optional[Dict[str, Any]] = None
    self.created_controller_objects: List[
        Dict[str, Any]
    ] = []
    # Independent transaction-local receipt ledger; names and legacy
    # created_controller_objects alone are not deletion authority.
    self._controller_receipt_seal = object()
    self._controller_creation_receipts: Dict[int, Tuple[Any, str, str, object]] = {}
    self.created_constraints: List[
        Dict[str, Any]
    ] = []
    # [INTRODUCED 2026-11-16T17:18:48+08:00]
    # FUNCTION: _ArmRigTransactionContext.__init__
    # PURPOSE: Establish independent receipt seal and receipt ledger for constraint creation
    # REASON: Task 10-B fix-4, require independent provenance receipts for constraint rollback authorization
    self._constraint_receipt_seal = object()
    self._constraint_creation_receipts: Dict[
        int, Tuple[Any, int, Any, int, str, str, object, FrozenSet[int]]
    ] = {}
    self.created_collection_links: List[
        Dict[str, Any]
    ] = []
    self.prepared_relationship_mutations: List[
        Dict[str, Any]
    ] = []
    self.stashed_objects: List[Dict[str, Any]] = []
    self.stashed_constraints: List[Dict[str, Any]] = []
    self.created_collections: List[Dict[str, Any]] = []
    self.uncleaned_stashed_objects: List[Dict[str, Any]] = []
    self.uncleaned_stashed_constraints: List[Dict[str, Any]] = []
    self.cleanup_error: Optional[str] = None
    self.rollback_only: bool = False
    self.rollback_only_reason: Optional[str] = None
    self.failure_class: Optional[str] = None
    self.isolation_record: Optional[Dict[str, Any]] = None
    self.pre_write_integrity_compromised: bool = False
    self.pre_write_integrity_reasons: List[str] = []
    self.tx_id: str = uuid.uuid4().hex[:8]
    self.datablock_authorizations: List[Dict[str, Any]] = []
    self.datablock_cleanup_outcomes: List[Dict[str, Any]] = []
    self.entry_object_ptrs: Optional[FrozenSet[int]] = None
    self.entry_collection_ptrs: Optional[FrozenSet[int]] = None
    self._collection_receipt_seal = object()
    self._collection_creation_receipts: Dict[int, Tuple[Any, Any, str, str, object]] = {}
    # BUG-10: identity/seal created only by _authorized_create_type_a_mesh.
    self._type_a_datablock_receipt_seal = object()
    self._type_a_datablock_receipts: Dict[int, Tuple[Any, str, str, object]] = {}
