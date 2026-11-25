"""Transaction Context state class migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-12)."""

from typing import Any, Callable, Dict, Optional

import bpy

from src.scene_transaction_integrity.layer2.collection_link_registry import (
    _register_created_collection_link,
)
from src.scene_transaction_integrity.layer2.collection_receipts import (
    _register_created_collection,
)
from src.scene_transaction_integrity.layer2.constraint_registration import (
    _register_created_constraint,
)
from src.scene_transaction_integrity.layer2.controller_receipts import (
    _register_created_controller,
)
from src.scene_transaction_integrity.layer2.datablock_cleanup_records import (
    _find_datablock_cleanup_authorization,
    _record_deleted_datablock_cleanup,
    _record_preserved_datablock_cleanup,
)
from src.scene_transaction_integrity.layer2.relationship_mutation_prepare import (
    _prepare_relationship_mutation,
)
from src.scene_transaction_integrity.layer2.relationship_mutation_state_update import (
    _update_relationship_mutation_state,
)
from src.scene_transaction_integrity.layer2.relationship_states import (
    _RelationshipOperationState,
)
from src.scene_transaction_integrity.layer2 import (
    session_identity as _session_identity,
)
from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)
from src.scene_transaction_integrity.layer2.transaction_context_init import (
    _initialize_arm_rig_transaction_context,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)


# [INTRODUCED 2026-11-24T21:45:30+08:00]
# NODE: 10-B / L2-12
# FUNCTION: _ArmRigTransactionContext
# PURPOSE: 持有完整事务上下文状态、单调状态标记、Layer 2 注册委托与显式回调驱动的 Cleanup 重试入口
# REASON: 将 _ArmRigTransactionContext 核心状态类迁入 Layer 2，作为全仓唯一的事务上下文实现所有者
class _ArmRigTransactionContext:
    """Active transaction execution state tracking."""

    _DEFAULT_CROSS_LAYER_CALLBACKS: Dict[str, Any] = {}

    def __init__(
        self,
        arm: bpy.types.Object,
        session_record: Optional[ArmatureSessionIdentityRecord] = None,
        *,
        ensure_armature_session_identity: Optional[
            Callable[[bpy.types.Object], ArmatureSessionIdentityRecord]
        ] = None,
    ) -> None:
        if ensure_armature_session_identity is None:
            ensure_armature_session_identity = self._DEFAULT_CROSS_LAYER_CALLBACKS.get(
                "ensure_armature_session_identity",
                _session_identity.ensure_armature_session_identity,
            )
        _initialize_arm_rig_transaction_context(
            self,
            arm,
            session_record=session_record,
            ensure_armature_session_identity=ensure_armature_session_identity,
        )

    @property
    def committed(self) -> bool:
        """Backward-compatibility property reflecting logical commit status."""
        return self.state in (_ArmRigTransactionState.COMMITTED, _ArmRigTransactionState.CLEANUP_PENDING)

    def mark_pre_write_evidence_insufficient(self, reason: str) -> None:
        """Explicitly mark pre-write recovery evidence as insufficient before snapshot completion."""
        self.pre_write_integrity_compromised = True
        norm = str(reason).strip() if reason is not None else "Pre-write recovery evidence insufficient"
        if norm not in self.pre_write_integrity_reasons:
            self.pre_write_integrity_reasons.append(norm)

    def mark_rollback_only(self, reason: str) -> None:
        """Monotonically mark this transaction context as rollback-only preserving the first failure reason."""
        normalized_reason = str(reason).strip() if reason is not None else ""
        if not normalized_reason:
            normalized_reason = "Unspecified nested transaction failure"
        if not self.rollback_only:
            self.rollback_only = True
            self.rollback_only_reason = normalized_reason
        elif not self.rollback_only_reason:
            self.rollback_only_reason = normalized_reason

    def prepare_relationship_mutation(
        self,
        source_reference: Any,
        target_reference: Any,
        original_relationship_state: Dict[str, Any],
        intended_mutation: str,
    ) -> Dict[str, Any]:
        """PREPARE stage: create and register a 7-state relationship operation log record before mutation."""
        return _prepare_relationship_mutation(
            self,
            source_reference,
            target_reference,
            original_relationship_state,
            intended_mutation,
        )

    def update_relationship_mutation_state(
        self,
        op_record: Dict[str, Any],
        new_state: _RelationshipOperationState,
    ) -> None:
        """Transition a relationship operation record across the approved 7-state machine."""
        return _update_relationship_mutation_state(
            self,
            op_record,
            new_state,
        )

    def register_created_controller(
        self,
        obj: bpy.types.Object,
        *,
        find_live_object_by_identity: Optional[Callable[..., Any]] = None,
        controller_role_for_name: Optional[Callable[..., Any]] = None,
    ) -> None:
        """Preserve the legacy API; attest an explicit creation in this ACTIVE tx.

        This registration is a trusted explicit transaction operation, not an
        automatically inferred permission from a controller name or a mutable
        created_controller_objects entry alone.
        """
        if find_live_object_by_identity is None:
            find_live_object_by_identity = self._DEFAULT_CROSS_LAYER_CALLBACKS["find_live_object_by_identity"]
        if controller_role_for_name is None:
            controller_role_for_name = self._DEFAULT_CROSS_LAYER_CALLBACKS["controller_role_for_name"]
        return _register_created_controller(
            self,
            obj,
            find_live_object_by_identity=find_live_object_by_identity,
            controller_role_for_name=controller_role_for_name,
        )

    # [INTRODUCED 2026-11-16T17:18:48+08:00]
    # FUNCTION: _ArmRigTransactionContext.register_created_constraint
    # PURPOSE: Enforce receipt verification and active transaction ownership before registering created constraints
    # REASON: Task 10-B fix-4, prevent unauthorized direct registration without independent creation receipt
    def register_created_constraint(
        self,
        pbone: bpy.types.PoseBone,
        con: bpy.types.Constraint,
        *,
        ensure_armature_session_identity: Optional[Callable[[bpy.types.Object], Any]] = None,
    ) -> None:
        """Register a constraint created by this transaction for identity-based ownership."""
        if ensure_armature_session_identity is None:
            ensure_armature_session_identity = self._DEFAULT_CROSS_LAYER_CALLBACKS.get(
                "ensure_armature_session_identity",
                _session_identity.ensure_armature_session_identity,
            )
        return _register_created_constraint(
            self,
            pbone,
            con,
            active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
            transaction_state_cls=_ArmRigTransactionState,
            ensure_armature_session_identity=ensure_armature_session_identity,
        )

    def register_created_collection_link(
        self,
        col: bpy.types.Collection,
        obj: bpy.types.Object,
    ) -> None:
        """Register an object-to-collection link mutation created by this transaction."""
        return _register_created_collection_link(
            self,
            col,
            obj,
        )

    def register_created_collection(
        self,
        col: bpy.types.Collection,
        initial_parent: Optional[bpy.types.Collection] = None,
        *,
        find_live_collection_by_identity: Optional[Callable[..., Any]] = None,
    ) -> None:
        """Attest a newly created, not-yet-linked Collection and intended parent."""
        if find_live_collection_by_identity is None:
            find_live_collection_by_identity = self._DEFAULT_CROSS_LAYER_CALLBACKS["find_live_collection_by_identity"]
        return _register_created_collection(
            self,
            col,
            initial_parent=initial_parent,
            find_live_collection_by_identity=find_live_collection_by_identity,
        )

    def retry_cleanup(
        self,
        *,
        execute_stashed_cleanup_pass: Optional[Callable[..., Any]] = None,
        authorized_remove_constraint: Optional[Callable[..., Any]] = None,
        cleanup_stashed_constraints: Optional[Callable[..., Any]] = None,
        cleanup_stashed_object: Optional[Callable[..., Any]] = None,
        trigger_fault_injection: Optional[Callable[..., None]] = None,
        remove_stashed_object_and_verify: Optional[Callable[..., Any]] = None,
        find_stashed_datablock: Optional[Callable[..., Any]] = None,
        remove_authorized_stashed_datablock: Optional[Callable[..., Any]] = None,
        build_cleanup_result: Optional[Callable[..., Any]] = None,
        cleanup_outcome_cls: Any = None,
        cleanup_result_cls: Any = None,
    ) -> Any:
        """Idempotently retry irreversible cleanup of pending stashed resources."""
        cbs = self._DEFAULT_CROSS_LAYER_CALLBACKS
        if execute_stashed_cleanup_pass is None:
            execute_stashed_cleanup_pass = cbs["execute_stashed_cleanup_pass"]
        if authorized_remove_constraint is None:
            authorized_remove_constraint = cbs["authorized_remove_constraint"]
        if cleanup_stashed_constraints is None:
            cleanup_stashed_constraints = cbs["cleanup_stashed_constraints"]
        if cleanup_stashed_object is None:
            cleanup_stashed_object = cbs["cleanup_stashed_object"]
        if trigger_fault_injection is None:
            trigger_fault_injection = cbs["trigger_fault_injection"]
        if remove_stashed_object_and_verify is None:
            remove_stashed_object_and_verify = cbs["remove_stashed_object_and_verify"]
        if find_stashed_datablock is None:
            find_stashed_datablock = cbs["find_stashed_datablock"]
        if remove_authorized_stashed_datablock is None:
            remove_authorized_stashed_datablock = cbs["remove_authorized_stashed_datablock"]
        if build_cleanup_result is None:
            build_cleanup_result = cbs["build_cleanup_result"]
        if cleanup_outcome_cls is None:
            cleanup_outcome_cls = cbs["cleanup_outcome_cls"]
        if cleanup_result_cls is None:
            cleanup_result_cls = cbs["cleanup_result_cls"]
        return execute_stashed_cleanup_pass(
            self,
            transaction_state_cls=_ArmRigTransactionState,
            authorized_remove_constraint=authorized_remove_constraint,
            cleanup_stashed_constraints=cleanup_stashed_constraints,
            cleanup_stashed_object=cleanup_stashed_object,
            trigger_fault_injection=trigger_fault_injection,
            remove_stashed_object_and_verify=remove_stashed_object_and_verify,
            find_stashed_datablock=find_stashed_datablock,
            find_datablock_cleanup_authorization=_find_datablock_cleanup_authorization,
            remove_authorized_stashed_datablock=remove_authorized_stashed_datablock,
            record_preserved_datablock_cleanup=_record_preserved_datablock_cleanup,
            record_deleted_datablock_cleanup=_record_deleted_datablock_cleanup,
            build_cleanup_result=build_cleanup_result,
            cleanup_outcome_cls=cleanup_outcome_cls,
            cleanup_result_cls=cleanup_result_cls,
        )
