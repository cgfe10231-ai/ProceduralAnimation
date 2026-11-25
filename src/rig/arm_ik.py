"""Procedural two-bone arm IK and independent hand orientation control (Task 6F-A / Task 10-A).

Builds on the existing 19-bone CharacterArmature from Task 4B and complements leg IK (Task 4C):
- Creates dedicated Empty control objects for left/right hand IK targets (`HandIK.L`, `HandIK.R`)
  and elbow pole targets (`ElbowPole.L`, `ElbowPole.R`).
- Configures Blender native `IK` constraints (`chain_count = 2`) on `forearm.L` and `forearm.R`
  so `upper_arm` + `forearm` form a deterministic two-bone IK chain per arm.
- Configures elbow flexion constraints and pre-bend solver hints with matched `pole_angle = -90.0 deg`
  to guarantee natural forward/inward elbow flexion and outward/backward olecranon projection.
- Configures native `COPY_ROTATION` constraints on `hand.L` and `hand.R` targeting `HandIK.L` / `HandIK.R`
  in world space, enabling independent 3D hand orientation control decoupled from IK arm solving.
- Zero-impact backward compatibility:
  - Bone hierarchy and naming are 100% preserved.
  - IK constraints and rotation constraints default to `influence = 0.0`.
  - When influence is 0.0, the armature evaluates 100% identical to the original FK arm swing.
- Programmatic API:
  - `setup_arm_ik(...)`: idempotent configuration of arm IK constraints and empties.
  - `set_hand_ik_target(...)`: sets independent world-space position, 3D hand rotation, and elbow pole.
  - `set_arm_ik_influence(...)`: smoothly blends between FK (0.0) and IK (1.0).
  - `reset_arm_ik(...)`: resets arm IK targets and sets influence back to 0.0.
  - `get_arm_ik_state(...)`: inspects actual bone lengths, target error, orientation error, and reachability.

Task 10-A Contracts:
- Setup Idempotency: setup_arm_ik() ensures controls and constraints exist with correct configuration,
  without resetting active positions, orientations, or influences.
- Explicit Reset: reset_arm_ik() actively restores neutral rest positions and influence=0.0 while
  respecting existing effective parent transforms and rotation modes.
- Effective Parent Matrix: M_eff = M_parent @ matrix_parent_inverse handles world translation and
  rotation inversion across arbitrary valid conformal parent hierarchies.
- Rotation Mode Fidelity: preserves controller active rotation_mode across 6 Euler modes, QUATERNION,
  and AXIS_ANGLE without forced conversion to XYZ.
- Dependency Graph Freshness: synchronizes view layer before computing effective parent matrices.
"""

import math
import time
import uuid
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import bpy
from mathutils import Color, Euler, Matrix, Quaternion, Vector

from src.rig.transform_utils import (
    apply_target_rotation,
    compute_effective_parent_matrix,
    validate_effective_parent_transform,
    world_to_local_position,
    world_to_local_rotation,
    world_to_local_rotation_quaternion,
)
from src.scene_transaction_integrity.layer1 import (
    _COORDINATOR_AUTHORIZATION_GRANTS,
    _COORDINATOR_GRANT_TTL_SECONDS,
    _admit_outermost_arm_rig_transaction as _layer1_admit_outermost_arm_rig_transaction,
    _arm_rig_transaction as _layer1_arm_rig_transaction,
    _assert_admission_identity_valid as _layer1_assert_admission_identity_valid,
    _assert_arm_rig_cleanup_gate as _layer1_assert_arm_rig_cleanup_gate,
    _assert_arm_rig_failed_isolation_gate as _layer1_assert_arm_rig_failed_isolation_gate,
    _assert_nested_transaction_admission as _layer1_assert_nested_transaction_admission,
    _capture_transaction_entry_fingerprint as _layer1_capture_transaction_entry_fingerprint,
    _clear_coordinator_authorization_grants as _layer1_clear_coordinator_authorization_grants,
    _commit_arm_rig_transaction as _layer1_commit_arm_rig_transaction,
    _confirm_cleanup_success as _layer1_confirm_cleanup_success,
    _coordinator_apply_cleanup_result as _layer1_coordinator_apply_cleanup_result,
    _coordinator_preserve_cleanup_pending as _layer1_coordinator_preserve_cleanup_pending,
    _coordinator_reap_stale_authorization_grants as _layer1_coordinator_reap_stale_authorization_grants,
    _coordinator_revoke_session_authorization_grants as _layer1_coordinator_revoke_session_authorization_grants,
    _coordinator_validate_cleanup_preflight as _layer1_coordinator_validate_cleanup_preflight,
    _coordinator_validate_cleanup_result_contract as _layer1_coordinator_validate_cleanup_result_contract,
    _dispatch_initial_post_commit_cleanup as _layer1_dispatch_initial_post_commit_cleanup,
    _establish_outermost_arm_rig_transaction as _layer1_establish_outermost_arm_rig_transaction,
    _identity_failure_is_uncertain,
    _issue_coordinator_authorization_grant as _layer1_issue_coordinator_authorization_grant,
    _release_active_arm_rig_transaction as _layer1_release_active_arm_rig_transaction,
    _safe_object_name,
    _snapshot_and_activate_transaction as _layer1_snapshot_and_activate_transaction,
    _sweep_dead_managed_armature_identities as _layer1_sweep_dead_managed_armature_identities,
    request_armature_deisolation as _layer1_request_armature_deisolation,
    retire_dead_armature_tombstone as _layer1_retire_dead_armature_tombstone,
    retry_pending_arm_rig_cleanup as _layer1_retry_pending_arm_rig_cleanup,
)
from src.scene_transaction_integrity.layer2 import (
    ArmatureSessionIdentityRecord,
    _ACTIVE_TRANSACTION_STACK,
    _ARCHIVED_FAILED_D_TOMBSTONES,
    _ArmRigTransactionContext as _Layer2ArmRigTransactionContext,
    _ArmRigTransactionState,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
    _DEISOLATION_AUDIT_LOG,
    _FAILED_A_AUDIT_RECORDS,
    _FailedTransactionClass,
    _ISOLATED_FAILED_ARMATURES,
    _LEGAL_RELATIONSHIP_LOG_TRANSITIONS,
    _MANAGED_ARMATURE_IDENTITIES,
    _PENDING_ARM_RIG_CLEANUPS,
    _RelationshipOperationState,
    _append_deisolation_audit,
    _check_original_object_liveness as _layer2_check_original_object_liveness,
    _clear_or_retire_failure_isolation_by_coordinator as _layer2_clear_or_retire_failure_isolation_by_coordinator,
    _find_datablock_cleanup_authorization as _layer2_find_datablock_cleanup_authorization,
    _initialize_arm_rig_transaction_context as _layer2_initialize_arm_rig_transaction_context,
    _prepare_relationship_mutation as _layer2_prepare_relationship_mutation,
    _record_armature_failure_isolation_by_coordinator as _layer2_record_armature_failure_isolation_by_coordinator,
    _record_deleted_datablock_cleanup as _layer2_record_deleted_datablock_cleanup,
    _record_failed_a_audit,
    _record_preserved_datablock_cleanup as _layer2_record_preserved_datablock_cleanup,
    _register_created_collection as _layer2_register_created_collection,
    _register_created_collection_link as _layer2_register_created_collection_link,
    _register_created_constraint as _layer2_register_created_constraint,
    _register_created_controller as _layer2_register_created_controller,
    _register_pending_arm_rig_cleanup as _layer2_register_pending_arm_rig_cleanup,
    _safe_object_pointer,
    _update_relationship_mutation_state as _layer2_update_relationship_mutation_state,
    _verify_armature_session_identity_record as _layer2_verify_armature_session_identity_record,
    ensure_armature_session_identity as _layer2_ensure_armature_session_identity,
    get_pending_arm_rig_cleanup_ids as _layer2_get_pending_arm_rig_cleanup_ids,
    query_admission_gate_status as _layer2_query_admission_gate_status,
)
from src.scene_transaction_integrity.layer3 import (
    ARM_IK_CONSTRAINT_NAMES,
    ExternalControllerNameConflictError,
    _TARGET_UNSET,
    _apply_single_constraint_target_unit as _layer3_apply_single_constraint_target_unit,
    _authorized_assign_constraint_targets as _layer3_authorized_assign_constraint_targets,
    _authorized_assign_object_parent as _layer3_authorized_assign_object_parent,
    _authorized_create_constraint as _layer3_authorized_create_constraint,
    _authorized_create_type_a_mesh as _layer3_authorized_create_type_a_mesh,
    _authorized_ensure_snapshot_collection_link as _layer3_authorized_ensure_snapshot_collection_link,
    _authorized_link_child_collection as _layer3_authorized_link_child_collection,
    _authorized_link_object_to_collection as _layer3_authorized_link_object_to_collection,
    _authorized_remove_constraint as _layer3_authorized_remove_constraint,
    _authorized_restore_collection_object_relationships as _layer3_authorized_restore_collection_object_relationships,
    _authorized_restore_relationship as _layer3_authorized_restore_relationship,
    _authorized_restore_snapshot_collection_child as _layer3_authorized_restore_snapshot_collection_child,
    _authorized_restore_snapshot_constraint_targets_without_tx as _layer3_authorized_restore_snapshot_constraint_targets_without_tx,
    _authorized_restore_snapshot_object_parent as _layer3_authorized_restore_snapshot_object_parent,
    _authorized_revert_relationship_record as _layer3_authorized_revert_relationship_record,
    _authorized_unlink_child_collection as _layer3_authorized_unlink_child_collection,
    _authorized_unlink_object_from_collection as _layer3_authorized_unlink_object_from_collection,
    _classify_constraint_target_pair_effect as _layer3_classify_constraint_target_pair_effect,
    _cleanup_failed_character_collection_registration as _layer3_cleanup_failed_character_collection_registration,
    _cleanup_failed_constraint_creation as _layer3_cleanup_failed_constraint_creation,
    _controller_constraint_binding_proven,
    _controller_is_borrowed_by_other_armature as _layer3_controller_is_borrowed_by_other_armature,
    _controller_role_for_name as _layer3_controller_role_for_name,
    _ensure_character_collection as _layer3_ensure_character_collection,
    _find_collection_by_name,
    _find_live_collection_by_identity as _layer3_find_live_collection_by_identity,
    _find_live_object_by_identity,
    _find_stashed_datablock as _layer3_find_stashed_datablock,
    _get_or_create_empty as _layer3_get_or_create_empty,
    _is_child_collection_linked_by_identity,
    _is_collection_descendant_of,
    _is_object_linked_to_collection_by_identity,
    _matrix_equals,
    _remove_authorized_stashed_datablock as _layer3_remove_authorized_stashed_datablock,
    _remove_stashed_object_and_verify as _layer3_remove_stashed_object_and_verify,
    _require_collection_child_relationship_ownership as _layer3_require_collection_child_relationship_ownership,
    _require_existing_arm_ik_controller_ownership as _layer3_require_existing_arm_ik_controller_ownership,
    _verify_controller_object_transaction_authority as _layer3_verify_controller_object_transaction_authority,
    _verify_failed_isolation_controller_recovery_authority as _layer3_verify_failed_isolation_controller_recovery_authority,
    _verify_transaction_wrong_type_object_ownership as _layer3_verify_transaction_wrong_type_object_ownership,
)
from src.scene_transaction_integrity.layer4 import (
    _apply_arm_ik_prebend_hint,
    _apply_arm_ik_prebend_hint_side,
    _clear_test_depsgraph_updater as _layer4_clear_test_depsgraph_updater,
    _depsgraph_update as _layer4_depsgraph_update,
    _preflight_arm_ik_parent_transforms as _layer4_preflight_arm_ik_parent_transforms,
    _resolve_armature,
    _set_test_depsgraph_updater as _layer4_set_test_depsgraph_updater,
    _update_arm_ik_depsgraph as _layer4_update_arm_ik_depsgraph,
    _validate_bool,
    _validate_influence,
    _validate_side,
    _validate_vec3,
    get_arm_ik_state as _layer4_get_arm_ik_state,
    reset_arm_ik as _layer4_reset_arm_ik,
    set_arm_ik_influence as _layer4_set_arm_ik_influence,
    set_hand_ik_target as _layer4_set_hand_ik_target,
    setup_arm_ik as _layer4_setup_arm_ik,
)
from src.scene_transaction_integrity.layer5 import (
    _capture_pre_snapshot_structural_fingerprint as _layer5_capture_pre_snapshot_structural_fingerprint,
    _clone_snapshot_property_value,
    _freeze_fingerprint_property_value,
    _has_nan_or_inf,
    _rollback_arm_rig_state as _layer5_rollback_arm_rig_state,
    _snapshot_arm_rig_state as _layer5_snapshot_arm_rig_state,
    _verify_arm_rig_state_restored as _layer5_verify_arm_rig_state_restored,
    _verify_dead_armature_tombstone_retirement_evidence as _layer5_verify_dead_armature_tombstone_retirement_evidence,
    _verify_pre_write_zero_mutation_and_integrity as _layer5_verify_pre_write_zero_mutation_and_integrity,
    verify_armature_deisolation_evidence as _layer5_verify_armature_deisolation_evidence,
)
from src.scene_transaction_integrity.layer6 import (
    _CleanupOutcome,
    _CleanupResult,
    _build_cleanup_result as _layer6_build_cleanup_result,
    _cleanup_stashed_constraints as _layer6_cleanup_stashed_constraints,
    _cleanup_stashed_object as _layer6_cleanup_stashed_object,
    _execute_stashed_cleanup_pass as _layer6_execute_stashed_cleanup_pass,
)

ARM_IK_TARGET_NAMES: Dict[str, str] = {"L": "HandIK.L", "R": "HandIK.R"}
ARM_POLE_TARGET_NAMES: Dict[str, str] = {"L": "ElbowPole.L", "R": "ElbowPole.R"}
HAND_ROT_CONSTRAINT_NAMES: Dict[str, str] = {"L": "HandRotation.L", "R": "HandRotation.R"}

# Segment geometry matching Task 4B specifications (meters)
SHOULDER_X_OFFSET: float = 0.24
SHOULDER_REST_Z: float = 1.54
ELBOW_REST_Z: float = 1.24
WRIST_REST_Z: float = 0.98
HAND_TIP_REST_Z: float = 0.88

UPPER_ARM_LENGTH: float = 0.30
FOREARM_LENGTH: float = 0.26
HAND_LENGTH: float = 0.10

MAX_ARM_REACH: float = UPPER_ARM_LENGTH + FOREARM_LENGTH  # 0.56 m
MIN_ARM_REACH: float = 0.08  # Minimum distance avoiding degenerate zero-length vectors

DEFAULT_POLE_BACKWARD_OFFSET: float = 0.40  # Meters backward (-Y) from arm plane
DEFAULT_POLE_OUTWARD_OFFSET: float = 0.08   # Meters outward (X) from arm plane


def _cleanup_failed_character_collection_registration(
    col: bpy.types.Collection,
    expected_ptr: int,
    initial_parent: bpy.types.Collection,
    active_tx: Any,
) -> None:
    """Compensate only an unregistered, proven-fresh Collection.

    Once a valid creation receipt exists, the enclosing transaction owns the
    deletion and will perform its authorized rollback. Never remove that
    Collection here or leave a stale receipt pointing at a destroyed ID.
    """
    return _layer3_cleanup_failed_character_collection_registration(
        col,
        expected_ptr,
        initial_parent,
        active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        is_child_collection_linked_by_identity=(
            _is_child_collection_linked_by_identity
        ),
    )


def _ensure_character_collection() -> bpy.types.Collection:
    """Ensure the Character collection exists in the active scene with strict registration-before-link order (F14-06)."""
    return _layer3_ensure_character_collection(
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        trigger_fault_injection=_trigger_fault_injection,
        cleanup_failed_character_collection_registration=_cleanup_failed_character_collection_registration,
        authorized_link_child_collection=_authorized_link_child_collection,
    )


# =============================================================================
# Production Transaction Snapshot, Rollback, and Verification Infrastructure
# =============================================================================

def _check_original_object_liveness(record: ArmatureSessionIdentityRecord) -> Dict[str, Any]:
    """Evaluate physical Blender Object existence (Eo) independently from data block identity (Ed)."""
    return _layer2_check_original_object_liveness(record)


def _verify_armature_session_identity_record(
    record: ArmatureSessionIdentityRecord,
    candidate_arm: Optional[bpy.types.Object] = None,
) -> Dict[str, Any]:
    """Simultaneously verify all 7 Armature session identity conditions (Task 10-B-13 Section 4.2)."""
    return _layer2_verify_armature_session_identity_record(
        record,
        candidate_arm=candidate_arm,
    )


def _sweep_dead_managed_armature_identities() -> None:
    """Refresh liveness of all registered ArmatureSessionIdentityRecords and escalate dead isolated armatures."""
    return _layer1_sweep_dead_managed_armature_identities(
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        armature_isolation_state_cls=_ArmatureIsolationState,
        failed_transaction_class_cls=_FailedTransactionClass,
        check_original_object_liveness=_check_original_object_liveness,
        verify_armature_session_identity_record=_verify_armature_session_identity_record,
    )


def ensure_armature_session_identity(arm: bpy.types.Object) -> ArmatureSessionIdentityRecord:
    """Layer 2: Resolve existing verified ArmatureSessionIdentityRecord or register a new session identity."""
    _sweep_dead_managed_armature_identities()
    return _layer2_ensure_armature_session_identity(arm)


def _record_armature_failure_isolation_by_coordinator(
    session_rec: ArmatureSessionIdentityRecord,
    tx: "_ArmRigTransactionContext",
    failure_class: _FailedTransactionClass,
    primary_exception: Optional[BaseException],
    secondary_exception: Optional[BaseException] = None,
    evidence_status: str = "SNAPSHOT_AVAILABLE",
    missing_evidence_reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Layer 2: Record FAILED-B / FAILED-C / FAILED-D isolation or tombstone under Layer 1 Coordinator authority."""
    return _layer2_record_armature_failure_isolation_by_coordinator(
        session_rec=session_rec,
        tx=tx,
        failure_class=failure_class,
        primary_exception=primary_exception,
        secondary_exception=secondary_exception,
        evidence_status=evidence_status,
        missing_evidence_reasons=missing_evidence_reasons,
        failed_transaction_class_cls=_FailedTransactionClass,
        armature_isolation_state_cls=_ArmatureIsolationState,
        armature_liveness_status_cls=_ArmatureLivenessStatus,
        relationship_operation_state_cls=_RelationshipOperationState,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        record_failed_a_audit=_record_failed_a_audit,
        check_original_object_liveness=_check_original_object_liveness,
    )


def _coordinator_reap_stale_authorization_grants() -> None:
    """Revoke expired, malformed, or provenance-stale grants without touching FAILED isolation."""
    _layer1_coordinator_reap_stale_authorization_grants(
        coordinator_authorization_grants=_COORDINATOR_AUTHORIZATION_GRANTS,
        coordinator_grant_ttl_seconds=_COORDINATOR_GRANT_TTL_SECONDS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
    )


def _coordinator_revoke_session_authorization_grants(session_id: str) -> None:
    """Invalidate all older grants for a session after a new issue or successful transition."""
    _layer1_coordinator_revoke_session_authorization_grants(
        session_id,
        coordinator_authorization_grants=_COORDINATOR_AUTHORIZATION_GRANTS,
    )


def _issue_coordinator_authorization_grant(
    session_id: str,
    transition_action: str = "CLEAR_TO_NONE",
    arm: Optional[bpy.types.Object] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Issue a single-use internal authorization grant binding verified Layer 5 recovery evidence."""
    return _layer1_issue_coordinator_authorization_grant(
        session_id,
        transition_action=transition_action,
        arm=arm,
        coordinator_authorization_grants=_COORDINATOR_AUTHORIZATION_GRANTS,
        coordinator_grant_ttl_seconds=_COORDINATOR_GRANT_TTL_SECONDS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        coordinator_reap_stale_authorization_grants=_coordinator_reap_stale_authorization_grants,
        coordinator_revoke_session_authorization_grants=_coordinator_revoke_session_authorization_grants,
        verify_deisolation_evidence=verify_armature_deisolation_evidence,
        verify_dead_armature_tombstone_retirement_evidence=_verify_dead_armature_tombstone_retirement_evidence,
        failed_transaction_class_cls=_FailedTransactionClass,
        armature_isolation_state_cls=_ArmatureIsolationState,
        legacy_kwargs=kwargs,
    )


def _clear_coordinator_authorization_grants() -> None:
    """Clear active Coordinator authorization grants (test fixture cleanup)."""
    _layer1_clear_coordinator_authorization_grants(
        coordinator_authorization_grants=_COORDINATOR_AUTHORIZATION_GRANTS,
    )


def _clear_or_retire_failure_isolation_by_coordinator(
    session_id: str,
    action: str,
    reason: str,
    authorization_grant: Optional[Dict[str, Any]] = None,
    verification_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer 2: Clear FAILED-B/C isolation or archive FAILED-D tombstone exclusively for Layer 1 Coordinator."""
    return _layer2_clear_or_retire_failure_isolation_by_coordinator(
        session_id,
        action,
        reason,
        authorization_grant=authorization_grant,
        verification_evidence=verification_evidence,
        archived_failed_d_tombstones=_ARCHIVED_FAILED_D_TOMBSTONES,
        coordinator_authorization_grants=_COORDINATOR_AUTHORIZATION_GRANTS,
        coordinator_grant_ttl_seconds=_COORDINATOR_GRANT_TTL_SECONDS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        coordinator_reap_stale_authorization_grants=_coordinator_reap_stale_authorization_grants,
        coordinator_revoke_session_authorization_grants=_coordinator_revoke_session_authorization_grants,
        verify_deisolation_evidence=verify_armature_deisolation_evidence,
        verify_dead_armature_tombstone_retirement_evidence=_verify_dead_armature_tombstone_retirement_evidence,
        armature_isolation_state_cls=_ArmatureIsolationState,
    )


_FAULT_INJECTION_HOOK: Optional[Callable[[str, Dict[str, Any]], None]] = None


def _set_test_fault_injection_hook(hook: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
    """Private test hook callback for deterministic fault injection during tests."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = hook


def _clear_test_fault_injection_hook() -> None:
    """Clear private internal test fault injection hook."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = None


def _trigger_fault_injection(stage: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Trigger internal fault injection if a hook is active."""
    global _FAULT_INJECTION_HOOK
    if _FAULT_INJECTION_HOOK is not None:
        _FAULT_INJECTION_HOOK(stage, context or {})


def _set_test_depsgraph_updater(updater: Optional[Callable[[], None]]) -> None:
    """Private test hook to replace or wrap depsgraph update execution at the boundary."""
    return _layer4_set_test_depsgraph_updater(updater)


def _clear_test_depsgraph_updater() -> None:
    """Clear private test depsgraph updater hook."""
    return _layer4_clear_test_depsgraph_updater()


def _depsgraph_update() -> None:
    """Internal unified dependency graph update boundary."""
    return _layer4_depsgraph_update()


def _update_arm_ik_depsgraph() -> None:
    """Synchronize the dependency graph for Arm IK calculations within mutations."""
    return _layer4_update_arm_ik_depsgraph(
        trigger_fault_injection=_trigger_fault_injection,
        depsgraph_update=_depsgraph_update,
    )


_REQUIRED_ARM_IK_BONE_NAMES: Tuple[str, ...] = (
    "upper_arm.L",
    "upper_arm.R",
    "forearm.L",
    "forearm.R",
    "hand.L",
    "hand.R",
)


def _capture_pre_snapshot_structural_fingerprint(arm: bpy.types.Object) -> Dict[str, Any]:
    """Capture a comprehensive read-only unrounded structural and value fingerprint before SNAPSHOTTING."""
    return _layer5_capture_pre_snapshot_structural_fingerprint(
        arm,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        required_arm_ik_bone_names=_REQUIRED_ARM_IK_BONE_NAMES,
    )


def _verify_pre_write_zero_mutation_and_integrity(
    arm: bpy.types.Object,
    pre_fp: Optional[Dict[str, Any]],
    tx: "_ArmRigTransactionContext",
) -> Dict[str, Any]:
    """Layer 5: Verify zero mutations and structural integrity when a transaction aborts before ACTIVE."""
    return _layer5_verify_pre_write_zero_mutation_and_integrity(
        arm=arm,
        pre_fp=pre_fp,
        tx=tx,
        transaction_state_cls=_ArmRigTransactionState,
        capture_pre_snapshot_structural_fingerprint=(
            _capture_pre_snapshot_structural_fingerprint
        ),
        has_nan_or_inf=_has_nan_or_inf,
        required_arm_ik_bone_names=_REQUIRED_ARM_IK_BONE_NAMES,
    )


def _snapshot_arm_rig_state(arm: bpy.types.Object) -> Dict[str, Any]:
    """Capture full production state snapshot of Arm IK controllers, pose bones, constraints, and collections.

    Zero-mutation guarantee: Strictly inspects and copies properties without modifying Blender state.
    """
    return _layer5_snapshot_arm_rig_state(
        arm,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        trigger_fault_injection=_trigger_fault_injection,
        depsgraph_update=_depsgraph_update,
        find_live_object_by_identity=_find_live_object_by_identity,
    )


def _find_live_collection_by_identity(
    col_ref: Optional[bpy.types.Collection],
    expected_ptr: Optional[int],
) -> Optional[bpy.types.Collection]:
    """Resolve the original live Blender Collection (user or scene master collection) by identity.

    A matching name alone never proves identity.
    """
    return _layer3_find_live_collection_by_identity(col_ref, expected_ptr)


def _authorized_link_object_to_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object link executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_authorized_link_object_to_collection(
        collection,
        obj,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        find_live_object_by_identity=_find_live_object_by_identity,
        is_object_linked_to_collection_by_identity=_is_object_linked_to_collection_by_identity,
        trigger_fault_injection=_trigger_fault_injection,
    )


def _authorized_unlink_object_from_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
    category: str = "TX_UNLINKED_ORIGINAL",
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object unlink executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_authorized_unlink_object_from_collection(
        collection,
        obj,
        active_tx=active_tx,
        category=category,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        relationship_operation_state_cls=_RelationshipOperationState,
        is_object_linked_to_collection_by_identity=_is_object_linked_to_collection_by_identity,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        find_live_object_by_identity=_find_live_object_by_identity,
        trigger_fault_injection=_trigger_fault_injection,
    )


def _controller_role_for_name(name: str) -> tuple[str, str] | None:
    """Resolve one of four Arm IK roles, never grant authority on its own."""
    return _layer3_controller_role_for_name(
        name,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
    )


def _controller_is_borrowed_by_other_armature(
    arm: bpy.types.Object,
    obj: bpy.types.Object,
    role: tuple[str, str],
) -> bool:
    """Deny a controller referenced by ANY constraint on another Armature.

    Retain the existing role parameter and the original Coordinator-owned
    permission path. Inspect all foreign Armature pose-bone and object
    constraints, not just a same-named IK constraint on forearm.L/R.
    """
    return _layer3_controller_is_borrowed_by_other_armature(
        arm,
        obj,
        role,
        find_live_object_by_identity=_find_live_object_by_identity,
    )


def _verify_controller_object_transaction_authority(
    obj: bpy.types.Object,
    tx: Any,
    *,
    created_only: bool = False,
) -> Optional[str]:
    """Check the existing transaction controller authorization boundary.

    TX_CREATED needs an independently minted registration receipt and absence
    from the entry pointer baseline. SNAPSHOT_ORIGINAL additionally needs a
    real original IK constraint binding, not merely a name-based snapshot.
    """
    return _layer3_verify_controller_object_transaction_authority(
        obj,
        tx,
        created_only=created_only,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        find_live_object_by_identity=_find_live_object_by_identity,
        controller_role_for_name=_controller_role_for_name,
        controller_constraint_binding_proven=_controller_constraint_binding_proven,
        controller_is_borrowed_by_other_armature=_controller_is_borrowed_by_other_armature,
    )


def _require_existing_arm_ik_controller_ownership(
    arm: bpy.types.Object,
    *,
    scope: str,
) -> None:
    """Read-only Arm IK ownership admission; never upgrade an active transaction.

    When a transaction is active, only its entry snapshot proof or its
    transaction-created receipt can authorize a controller. A constraint
    assigned *after* transaction entry cannot retroactively authorize an
    originally unrelated same-name Empty. Outside transactions, established
    live Arm IK bindings remain the backwards-compatible proof of ownership.
    Unbound pre-existing Empties fail closed: their ownership is unknowable.
    """
    return _layer3_require_existing_arm_ik_controller_ownership(
        arm,
        scope=scope,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        find_live_object_by_identity=_find_live_object_by_identity,
        verify_controller_object_transaction_authority=_verify_controller_object_transaction_authority,
        controller_role_for_name=_controller_role_for_name,
        controller_constraint_binding_proven=_controller_constraint_binding_proven,
        controller_is_borrowed_by_other_armature=_controller_is_borrowed_by_other_armature,
    )

def _authorized_assign_object_parent(
    obj: bpy.types.Object,
    parent: Optional[bpy.types.Object],
    matrix_parent_inverse: Optional[Matrix] = None,
    active_tx: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Object Parent and Matrix Parent Inverse assignment under 7-state protocol."""
    return _layer3_authorized_assign_object_parent(
        obj,
        parent,
        matrix_parent_inverse=matrix_parent_inverse,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_object_by_identity=_find_live_object_by_identity,
        verify_controller_object_transaction_authority=_verify_controller_object_transaction_authority,
        matrix_equals=_matrix_equals,
        validate_effective_parent_transform=validate_effective_parent_transform,
        trigger_fault_injection=_trigger_fault_injection,
        matrix_cls=Matrix,
    )


def _require_collection_child_relationship_ownership(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Any,
    *,
    unlink: bool,
) -> None:
    """Admit writes only to an original-parent edge of a proven TX-created child.

    A live reference, a Collection name, or an unsealed created_collections
    registry entry is not sufficient to establish mutation authority.
    """
    return _layer3_require_collection_child_relationship_ownership(
        parent_collection,
        child_collection,
        active_tx,
        unlink=unlink,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        relationship_operation_state_cls=_RelationshipOperationState,
    )


def _authorized_link_child_collection(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Optional[Any] = None,
    category: str = "TX_ADDED",
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection child linking executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_authorized_link_child_collection(
        parent_collection,
        child_collection,
        active_tx=active_tx,
        category=category,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        is_collection_descendant_of=_is_collection_descendant_of,
        is_child_collection_linked_by_identity=_is_child_collection_linked_by_identity,
        require_collection_child_relationship_ownership=_require_collection_child_relationship_ownership,
        trigger_fault_injection=_trigger_fault_injection,
        relationship_operation_state_cls=_RelationshipOperationState,
    )


def _authorized_unlink_child_collection(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Optional[Any] = None,
    category: str = "TX_UNLINKED_ORIGINAL",
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection child unlinking executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_authorized_unlink_child_collection(
        parent_collection,
        child_collection,
        active_tx=active_tx,
        category=category,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        is_child_collection_linked_by_identity=_is_child_collection_linked_by_identity,
        require_collection_child_relationship_ownership=_require_collection_child_relationship_ownership,
        trigger_fault_injection=_trigger_fault_injection,
    )


def _authorized_restore_relationship(
    active_tx: Optional[Any],
    snapshot: Optional[Dict[str, Any]],
    restoration_errors: List[str],
    mutation_type: Optional[str] = None,
) -> None:
    """Authoritatively revert and restore relationships via Layer 3 records."""
    return _layer3_authorized_restore_relationship(
        active_tx,
        snapshot,
        restoration_errors,
        mutation_type=mutation_type,
        authorized_revert_relationship_record=_authorized_revert_relationship_record,
    )


def _cleanup_failed_constraint_creation(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    expected_ptr: int,
    pbone_ptr: int,
    before_ptrs: frozenset[int],
    active_tx: Any,
) -> None:
    """Compensate an unregistered C-API creation; leave registered IDs to rollback.

    Never use a constraint name to select an object for destructive cleanup.
    An ambiguous partial registration is NOT permission to delete.
    """
    return _layer3_cleanup_failed_constraint_creation(
        pbone,
        con,
        expected_ptr,
        pbone_ptr,
        before_ptrs,
        active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
    )


def _authorized_create_constraint(
    pbone: bpy.types.PoseBone,
    con_type: str,
    con_name: str,
    active_tx: Optional[Any] = None,
    arm: Optional[bpy.types.Object] = None,
) -> bpy.types.Constraint:
    """Layer 3 authorized creation of a managed constraint on a pose bone.

    Enforces:
    1. Active transaction in ACTIVE state.
    2. Armature session identity matches transaction.
    3. Pose bone belongs to armature.
    4. Pose bone identity is live and verifiable.
    5. Constraint type must be 'IK' or 'COPY_ROTATION'.
    6. No duplicate live constraint with same identity and type.
    7. Immediate registration before any property assignment.
    8. Safe cleanup if registration fails.
    """
    return _layer3_authorized_create_constraint(
        pbone,
        con_type,
        con_name,
        active_tx=active_tx,
        arm=arm,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        ensure_armature_session_identity=ensure_armature_session_identity,
        trigger_fault_injection=_trigger_fault_injection,
        cleanup_failed_constraint_creation=_cleanup_failed_constraint_creation,
    )


def _authorized_remove_constraint(
    pbone: bpy.types.PoseBone,
    con_record_or_ref: Any,
    phase: str,
    active_tx: Optional[Any] = None,
) -> bool:
    """Layer 3 authoritative removal of a managed constraint.

    Only allowed in:
    1. phase == "ROLLBACK": for constraints in active_tx.created_constraints.
    2. phase == "POST_COMMIT_CLEANUP": for constraints in active_tx.stashed_constraints.

    Requires joint verification of:
    - live reference
    - pointer identity
    - owning pose bone
    - transaction registration record
    """
    return _layer3_authorized_remove_constraint(
        pbone,
        con_record_or_ref,
        phase,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        trigger_fault_injection=_trigger_fault_injection,
    )


def _classify_constraint_target_pair_effect(
    current_target: Optional[bpy.types.Object],
    current_subtarget: str,
    orig_target: Optional[bpy.types.Object],
    orig_target_ptr: Optional[int],
    orig_subtarget: str,
    dest_target: Optional[bpy.types.Object],
    dest_target_ptr: Optional[int],
    dest_subtarget: str,
) -> _RelationshipOperationState:
    """Classify two-field RNA state conservatively after interrupted target writes.

    NO_EFFECT is allowed ONLY for an exact original target AND subtarget pair.
    A recognized partial or complete write must stay reversible (APPLIED_VERIFIED).
    A third-party value or unreadable identity is RECOVERY_UNCERTAIN.
    """
    return _layer3_classify_constraint_target_pair_effect(
        current_target,
        current_subtarget,
        orig_target,
        orig_target_ptr,
        orig_subtarget,
        dest_target,
        dest_target_ptr,
        dest_subtarget,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_object_by_identity=_find_live_object_by_identity,
    )


def _apply_single_constraint_target_unit(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    field: str,
    subtarget_field: str,
    target_obj: Optional[bpy.types.Object],
    target_subtarget: str,
    intended_mutation: str,
    active_tx: Optional[Any],
) -> Optional[Dict[str, Any]]:
    """Execute a single constraint target or pole target assignment unit under 7-state protocol."""
    return _layer3_apply_single_constraint_target_unit(
        pbone,
        con,
        field,
        subtarget_field,
        target_obj,
        target_subtarget,
        intended_mutation,
        active_tx,
        find_live_object_by_identity=_find_live_object_by_identity,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_trigger_fault_injection,
    )


def _authorized_assign_constraint_targets(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    target: Any = _TARGET_UNSET,
    subtarget: Any = _TARGET_UNSET,
    pole_target: Any = _TARGET_UNSET,
    pole_subtarget: Any = _TARGET_UNSET,
    active_tx: Optional[Any] = None,
) -> None:
    """Layer 3 authorized constraint target and pole target assignment.

    Applies the 7-state relation machine (PREPARE -> APPLY -> VERIFY -> CONFIRM)
    for each target/subtarget relationship mutation unit.
    """
    return _layer3_authorized_assign_constraint_targets(
        pbone,
        con,
        target=target,
        subtarget=subtarget,
        pole_target=pole_target,
        pole_subtarget=pole_subtarget,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        find_live_object_by_identity=_find_live_object_by_identity,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_trigger_fault_injection,
    )


def _authorized_revert_relationship_record(
    op_record: Dict[str, Any],
    active_tx: Any,
    restoration_errors: List[str],
) -> None:
    """Layer 3 atomic reversal of a single relationship operation record."""
    return _layer3_authorized_revert_relationship_record(
        op_record,
        active_tx,
        restoration_errors,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_trigger_fault_injection,
        find_live_object_by_identity=_find_live_object_by_identity,
        classify_constraint_target_pair_effect=_classify_constraint_target_pair_effect,
        matrix_equals=_matrix_equals,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        is_child_collection_linked_by_identity=_is_child_collection_linked_by_identity,
        is_object_linked_to_collection_by_identity=_is_object_linked_to_collection_by_identity,
        bpy_module=bpy,
        matrix_cls=Matrix,
    )


def _authorized_restore_snapshot_collection_child(
    parent_ref: bpy.types.Collection,
    parent_ptr: int,
    child_ref: bpy.types.Collection,
    child_ptr: int,
    restoration_errors: List[str],
) -> None:
    """Restore a baseline Collection hierarchy edge by original live identity."""
    return _layer3_authorized_restore_snapshot_collection_child(
        parent_ref,
        parent_ptr,
        child_ref,
        child_ptr,
        restoration_errors,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        is_child_collection_linked_by_identity=_is_child_collection_linked_by_identity,
    )


def _authorized_ensure_snapshot_collection_link(
    col: Optional[bpy.types.Collection],
    obj_ref: bpy.types.Object,
    obj_ptr: Optional[int],
    restoration_errors: List[str],
) -> None:
    """Layer 3 restoration of a pre-existing snapshot Collection <-> Object membership by verified identity."""
    return _layer3_authorized_ensure_snapshot_collection_link(
        col,
        obj_ref,
        obj_ptr,
        restoration_errors,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        find_live_object_by_identity=_find_live_object_by_identity,
        is_object_linked_to_collection_by_identity=_is_object_linked_to_collection_by_identity,
    )


def _authorized_restore_collection_object_relationships(
    active_tx: Optional[Any],
    snapshot: Dict[str, Any],
    restoration_errors: List[str],
    phase: str = "ALL",
) -> None:
    """Layer 3 authoritative rollback and restoration of Collection <-> Object relationships."""
    return _layer3_authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase=phase,
        authorized_revert_relationship_record=_authorized_revert_relationship_record,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        find_live_object_by_identity=_find_live_object_by_identity,
        is_object_linked_to_collection_by_identity=_is_object_linked_to_collection_by_identity,
        verify_controller_object_transaction_authority=_verify_controller_object_transaction_authority,
        authorized_ensure_snapshot_collection_link=_authorized_ensure_snapshot_collection_link,
    )


def _authorized_restore_snapshot_object_parent(
    obj_ref: bpy.types.Object,
    obj_ptr: int,
    parent_ref: Optional[bpy.types.Object],
    parent_ptr: Optional[int],
    orig_inverse: Any,
    restoration_errors: List[str],
) -> None:
    """Restore a snapshot parent relationship only with proved live identities."""
    return _layer3_authorized_restore_snapshot_object_parent(
        obj_ref,
        obj_ptr,
        parent_ref,
        parent_ptr,
        orig_inverse,
        restoration_errors,
        find_live_object_by_identity=_find_live_object_by_identity,
        matrix_equals=_matrix_equals,
    )


def _authorized_restore_snapshot_constraint_targets_without_tx(
    con: bpy.types.Constraint,
    sc: Dict[str, Any],
    bone_name: str,
    restoration_errors: List[str],
) -> None:
    """Restore snapshot Constraint target pairs, refusing unproved Blender identities.

    All original target identities and BOTH field pairs are checked before writes.
    If a setter fails or verification fails, attempt a compensating restoration
    of the pre-call state and ALWAYS record a rollback error (never claim success).
    """
    return _layer3_authorized_restore_snapshot_constraint_targets_without_tx(
        con,
        sc,
        bone_name,
        restoration_errors,
        find_live_object_by_identity=_find_live_object_by_identity,
    )


def _verify_failed_isolation_controller_recovery_authority(
    arm: bpy.types.Object,
    obj: bpy.types.Object,
    snapshot: Dict[str, Any],
    tx: Any,
    expected_role: Optional[tuple[str, str]],
) -> tuple[bool, str]:
    """Verify that a FAILED-isolated transaction holds legal authority to restore original Controller state."""
    return _layer3_verify_failed_isolation_controller_recovery_authority(
        arm,
        obj,
        snapshot,
        tx,
        expected_role,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        failed_transaction_class_cls=_FailedTransactionClass,
        armature_isolation_state_cls=_ArmatureIsolationState,
        armature_liveness_status_cls=_ArmatureLivenessStatus,
        verify_armature_session_identity_record=_verify_armature_session_identity_record,
        find_live_object_by_identity=_find_live_object_by_identity,
        controller_role_for_name=_controller_role_for_name,
        controller_constraint_binding_proven=_controller_constraint_binding_proven,
        controller_is_borrowed_by_other_armature=_controller_is_borrowed_by_other_armature,
    )


def _rollback_arm_rig_state(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Restore the Arm IK rig state precisely to the recorded snapshot."""
    return _layer5_rollback_arm_rig_state(
        arm=arm,
        snapshot=snapshot,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        transaction_state_cls=_ArmRigTransactionState,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_trigger_fault_injection,
        authorized_revert_relationship_record=(
            _authorized_revert_relationship_record
        ),
        authorized_restore_collection_object_relationships=(
            _authorized_restore_collection_object_relationships
        ),
        controller_role_for_name=_controller_role_for_name,
        find_live_object_by_identity=_find_live_object_by_identity,
        verify_controller_object_transaction_authority=(
            _verify_controller_object_transaction_authority
        ),
        controller_is_borrowed_by_other_armature=(
            _controller_is_borrowed_by_other_armature
        ),
        verify_failed_isolation_controller_recovery_authority=(
            _verify_failed_isolation_controller_recovery_authority
        ),
        authorized_restore_snapshot_object_parent=(
            _authorized_restore_snapshot_object_parent
        ),
        matrix_equals=_matrix_equals,
        authorized_remove_constraint=_authorized_remove_constraint,
        authorized_restore_snapshot_constraint_targets_without_tx=(
            _authorized_restore_snapshot_constraint_targets_without_tx
        ),
        find_live_collection_by_identity=_find_live_collection_by_identity,
        is_child_collection_linked_by_identity=(
            _is_child_collection_linked_by_identity
        ),
        authorized_restore_snapshot_collection_child=(
            _authorized_restore_snapshot_collection_child
        ),
        authorized_ensure_snapshot_collection_link=(
            _authorized_ensure_snapshot_collection_link
        ),
        depsgraph_update=_depsgraph_update,
    )


def _verify_arm_rig_state_restored(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Verify that current Arm IK rig state precisely matches the snapshot.

    Raises:
        RuntimeError: If any discrepancy is detected between current state and snapshot.
    """
    return _layer5_verify_arm_rig_state_restored(
        arm=arm,
        snapshot=snapshot,
        active_tx=active_tx,
        snapshot_arm_rig_state=_snapshot_arm_rig_state,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        relationship_operation_state_cls=_RelationshipOperationState,
    )



# BUG-10: the only positive Type-A DataBlock authority issuer.
# It physically creates the Mesh before minting a transaction-bound receipt.
def _authorized_create_type_a_mesh(name: str, active_tx: Any) -> bpy.types.Mesh:
    """Create a transaction-owned Mesh with an identity-bound deletion receipt.

    Only this creation-returned Blender ID can receive TYPE_A_TX_CREATED
    authority. Observing an existing ID or appending an authorization dict
    never proves transaction creation.
    """
    return _layer3_authorized_create_type_a_mesh(
        name,
        active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
    )

class _ArmRigTransactionContext(_Layer2ArmRigTransactionContext):
    """Active transaction execution state tracking."""

    def __init__(
        self,
        arm: bpy.types.Object,
        session_record: Optional[ArmatureSessionIdentityRecord] = None,
    ):
        super().__init__(
            arm,
            session_record=session_record,
            ensure_armature_session_identity=ensure_armature_session_identity,
        )

    def register_created_controller(
        self,
        obj: bpy.types.Object,
    ) -> None:
        """Preserve the legacy API; attest an explicit creation in this ACTIVE tx.

        This registration is a trusted explicit transaction operation, not an
        automatically inferred permission from a controller name or a mutable
        created_controller_objects entry alone.
        """
        return super().register_created_controller(
            obj,
            find_live_object_by_identity=(
                _find_live_object_by_identity
            ),
            controller_role_for_name=(
                _controller_role_for_name
            ),
        )

    def register_created_constraint(
        self,
        pbone: bpy.types.PoseBone,
        con: bpy.types.Constraint,
    ) -> None:
        """Register a constraint created by this transaction for identity-based ownership."""
        return super().register_created_constraint(
            pbone,
            con,
            ensure_armature_session_identity=ensure_armature_session_identity,
        )

    def register_created_collection(
        self,
        col: bpy.types.Collection,
        initial_parent: Optional[bpy.types.Collection] = None,
    ) -> None:
        """Attest a newly created, not-yet-linked Collection and intended parent."""
        return super().register_created_collection(
            col,
            initial_parent=initial_parent,
            find_live_collection_by_identity=(
                _find_live_collection_by_identity
            ),
        )

    def retry_cleanup(self) -> _CleanupResult:
        """Idempotently retry irreversible cleanup of pending stashed resources."""
        return super().retry_cleanup(
            execute_stashed_cleanup_pass=_layer6_execute_stashed_cleanup_pass,
            authorized_remove_constraint=_authorized_remove_constraint,
            cleanup_stashed_constraints=_layer6_cleanup_stashed_constraints,
            cleanup_stashed_object=_layer6_cleanup_stashed_object,
            trigger_fault_injection=_trigger_fault_injection,
            remove_stashed_object_and_verify=(
                _layer3_remove_stashed_object_and_verify
            ),
            find_stashed_datablock=_layer3_find_stashed_datablock,
            remove_authorized_stashed_datablock=(
                _layer3_remove_authorized_stashed_datablock
            ),
            build_cleanup_result=_layer6_build_cleanup_result,
            cleanup_outcome_cls=_CleanupOutcome,
            cleanup_result_cls=_CleanupResult,
        )


def _coordinator_validate_cleanup_preflight(
    tx: "_ArmRigTransactionContext",
    phase: str,
) -> None:
    """Authorize cleanup BEFORE its first destructive resource operation.

    This is the Coordinator's phase-admission decision, distinct from the
    post-operation CleanupResult validator. It performs no resource deletion,
    relationship mutation, gate clearing, or transaction-state transition.
    An unknown live identity or an isolation mismatch must fail closed.
    """
    return _layer1_coordinator_validate_cleanup_preflight(
        tx,
        phase,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        armature_isolation_state_cls=_ArmatureIsolationState,
        verify_armature_session_identity_record=_verify_armature_session_identity_record,
    )


def _coordinator_validate_cleanup_result_contract(
    tx: "_ArmRigTransactionContext",
    result: "_CleanupResult",
    phase: str,
) -> None:
    """Validate the exact outcome contract BEFORE any lifecycle mutation.

    This routine does not repair a malformed result, infer a missing outcome,
    mutate the registry, or translate an invalid result into CLEANUP_SUCCESS.
    """
    return _layer1_coordinator_validate_cleanup_result_contract(
        tx,
        result,
        phase,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        cleanup_result_cls=_CleanupResult,
        cleanup_outcome_cls=_CleanupOutcome,
    )


def _coordinator_preserve_cleanup_pending(
    tx: "_ArmRigTransactionContext",
    error: BaseException,
) -> None:
    """Fail closed after logical commit without clobbering another transaction.

    Used by the initial cleanup exception paths. Never changes FAILED to
    COMMITTED/PENDING, never removes a FAILED isolation, and never pops a gate.
    In an impossible registry-key collision, raise rather than overwrite it.
    """
    return _layer1_coordinator_preserve_cleanup_pending(
        tx,
        error,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        register_pending_arm_rig_cleanup=_register_pending_arm_rig_cleanup,
    )


def _coordinator_apply_cleanup_result(
    tx: "_ArmRigTransactionContext",
    result: "_CleanupResult",
    phase: str,
) -> None:
    """Exclusively decide cleanup state after full result/identity validation.

    No malformed result, uncertain Armature, or FAILED isolation may be treated
    as success; rejection is reported, not swallowed or coerced to NO_EFFECT.
    """
    return _layer1_coordinator_apply_cleanup_result(
        tx,
        result,
        phase,
        coordinator_validate_cleanup_result_contract=(
            _coordinator_validate_cleanup_result_contract
        ),
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        armature_isolation_state_cls=_ArmatureIsolationState,
        transaction_state_cls=_ArmRigTransactionState,
        cleanup_outcome_cls=_CleanupOutcome,
        verify_armature_session_identity_record=_verify_armature_session_identity_record,
        confirm_cleanup_success=_layer1_confirm_cleanup_success,
        coordinator_preserve_cleanup_pending=_coordinator_preserve_cleanup_pending,
    )


def _register_pending_arm_rig_cleanup(
    tx: "_ArmRigTransactionContext",
) -> None:
    return _layer2_register_pending_arm_rig_cleanup(
        tx,
        transaction_state_cls=_ArmRigTransactionState,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
    )


def get_pending_arm_rig_cleanup_ids() -> Tuple[str, ...]:
    """Return pending cleanup transaction IDs."""
    return _layer2_get_pending_arm_rig_cleanup_ids(
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
    )


def retry_pending_arm_rig_cleanup(tx_id: str) -> None:
    """Retry cleanup of one pending transaction."""
    return _layer1_retry_pending_arm_rig_cleanup(
        tx_id,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        transaction_state_cls=_ArmRigTransactionState,
        coordinator_validate_cleanup_preflight=_coordinator_validate_cleanup_preflight,
        coordinator_apply_cleanup_result=_coordinator_apply_cleanup_result,
    )


def _assert_arm_rig_cleanup_gate(
    arm: bpy.types.Object,
    session_record: Optional[ArmatureSessionIdentityRecord] = None,
) -> None:
    """
    Reject new independent writes while the same Armature
    owns an unresolved committed cleanup transaction.
    """
    return _layer1_assert_arm_rig_cleanup_gate(
        arm,
        session_record,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        safe_object_pointer=_safe_object_pointer,
        transaction_state_cls=_ArmRigTransactionState,
    )


def _assert_arm_rig_failed_isolation_gate(
    arm: bpy.types.Object,
    session_record: ArmatureSessionIdentityRecord,
) -> None:
    """
    Reject new independent writes while the same Armature session identity
    is isolated in _ISOLATED_FAILED_ARMATURES (FAILED-B / FAILED-C / FAILED-D).
    """
    return _layer1_assert_arm_rig_failed_isolation_gate(
        arm,
        session_record,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        armature_isolation_state_cls=_ArmatureIsolationState,
        failed_transaction_class_cls=_FailedTransactionClass,
    )


def query_admission_gate_status(
    arm: Optional[bpy.types.Object] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Layer 2: Read-only query of unified admission gate status for an Armature or session_id."""
    _sweep_dead_managed_armature_identities()
    return _layer2_query_admission_gate_status(
        arm,
        session_id,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        archived_failed_d_tombstones=_ARCHIVED_FAILED_D_TOMBSTONES,
        armature_liveness_status_cls=_ArmatureLivenessStatus,
        armature_isolation_state_cls=_ArmatureIsolationState,
        safe_object_pointer=_safe_object_pointer,
        verify_armature_session_identity_record=_verify_armature_session_identity_record,
    )


def verify_armature_deisolation_evidence(
    arm: Optional[bpy.types.Object] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Layer 5: Read-only verification of recovery evidence before de-isolating an Armature (Section 8.2)."""
    return _layer5_verify_armature_deisolation_evidence(
        arm=arm,
        session_id=session_id,
        sweep_dead_managed_armature_identities=(
            _sweep_dead_managed_armature_identities
        ),
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        archived_failed_d_tombstones=_ARCHIVED_FAILED_D_TOMBSTONES,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        armature_liveness_status_cls=_ArmatureLivenessStatus,
        armature_isolation_state_cls=_ArmatureIsolationState,
        failed_transaction_class_cls=_FailedTransactionClass,
        relationship_operation_state_cls=_RelationshipOperationState,
        verify_armature_session_identity_record=(
            _verify_armature_session_identity_record
        ),
        verify_arm_rig_state_restored=_verify_arm_rig_state_restored,
        find_live_object_by_identity=_find_live_object_by_identity,
        find_live_collection_by_identity=_find_live_collection_by_identity,
    )


def _verify_dead_armature_tombstone_retirement_evidence(session_id: str) -> Dict[str, Any]:
    """Layer 5: Read-only verification of dead Armature tombstone retirement conditions (Section 8.2 Case 3)."""
    return _layer5_verify_dead_armature_tombstone_retirement_evidence(
        session_id=session_id,
        sweep_dead_managed_armature_identities=(
            _sweep_dead_managed_armature_identities
        ),
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        failed_transaction_class_cls=_FailedTransactionClass,
        armature_isolation_state_cls=_ArmatureIsolationState,
        check_original_object_liveness=_check_original_object_liveness,
        find_live_object_by_identity=_find_live_object_by_identity,
        find_live_collection_by_identity=_find_live_collection_by_identity,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
    )


def request_armature_deisolation(
    arm: Optional[bpy.types.Object],
    reason: str,
    session_id: Optional[str] = None,
    raise_on_reject: bool = False,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Evaluate Layer 5 evidence and authorize or reject de-isolation (Section 8.1/8.3)."""
    return _layer1_request_armature_deisolation(
        arm=arm,
        reason=reason,
        session_id=session_id,
        raise_on_reject=raise_on_reject,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        verify_deisolation_evidence=verify_armature_deisolation_evidence,
        issue_coordinator_authorization_grant=(
            _issue_coordinator_authorization_grant
        ),
        clear_or_retire_failure_isolation_by_coordinator=(
            _clear_or_retire_failure_isolation_by_coordinator
        ),
        append_deisolation_audit=_append_deisolation_audit,
    )


def retire_dead_armature_tombstone(
    session_id: str,
    reason: str,
    raise_on_reject: bool = False,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Verify dead Armature tombstone retirement evidence and transition to ARCHIVED_RETIRED."""
    return _layer1_retire_dead_armature_tombstone(
        session_id=session_id,
        reason=reason,
        raise_on_reject=raise_on_reject,
        verify_dead_armature_tombstone_retirement_evidence=(
            _verify_dead_armature_tombstone_retirement_evidence
        ),
        issue_coordinator_authorization_grant=(
            _issue_coordinator_authorization_grant
        ),
        clear_or_retire_failure_isolation_by_coordinator=(
            _clear_or_retire_failure_isolation_by_coordinator
        ),
        append_deisolation_audit=_append_deisolation_audit,
    )


@contextmanager
def _arm_rig_transaction(arm: bpy.types.Object):
    """Context manager executing Arm IK mutations under atomic transaction protection."""
    yield from _layer1_arm_rig_transaction(
        arm,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_state_cls=_ArmRigTransactionState,
        failed_transaction_class_cls=_FailedTransactionClass,
        relationship_operation_state_cls=_RelationshipOperationState,
        ensure_armature_session_identity=ensure_armature_session_identity,
        assert_arm_rig_cleanup_gate=_assert_arm_rig_cleanup_gate,
        assert_arm_rig_failed_isolation_gate=_assert_arm_rig_failed_isolation_gate,
        verify_armature_session_identity_record=(
            _verify_armature_session_identity_record
        ),
        record_armature_failure_isolation_by_coordinator=(
            _record_armature_failure_isolation_by_coordinator
        ),
        trigger_fault_injection=_trigger_fault_injection,
        capture_pre_snapshot_structural_fingerprint=(
            _capture_pre_snapshot_structural_fingerprint
        ),
        snapshot_arm_rig_state=_snapshot_arm_rig_state,
        depsgraph_update=_depsgraph_update,
        rollback_arm_rig_state=_rollback_arm_rig_state,
        verify_arm_rig_state_restored=_verify_arm_rig_state_restored,
        verify_pre_write_zero_mutation_and_integrity=(
            _verify_pre_write_zero_mutation_and_integrity
        ),
        coordinator_validate_cleanup_preflight=(
            _coordinator_validate_cleanup_preflight
        ),
        coordinator_preserve_cleanup_pending=(
            _coordinator_preserve_cleanup_pending
        ),
        coordinator_apply_cleanup_result=(
            _coordinator_apply_cleanup_result
        ),
    )


def _verify_transaction_wrong_type_object_ownership(
    obj: bpy.types.Object,
    tx: Optional['_ArmRigTransactionContext'],
    arm: Optional[bpy.types.Object] = None,
) -> bool:
    """Only current transaction-created objects may be replaced by controller name."""
    return _layer3_verify_transaction_wrong_type_object_ownership(
        obj,
        tx,
        arm,
        transaction_state_cls=_ArmRigTransactionState,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        verify_controller_object_transaction_authority=_verify_controller_object_transaction_authority,
    )


def _get_or_create_empty(
    name: str,
    display_type: str,
    display_size: float,
    parent: Optional[bpy.types.Object],
    collection: bpy.types.Collection,
) -> Tuple[bpy.types.Object, bool]:
    """Retrieve or construct an Empty control object preserving existing parent and transform.

    Returns:
        Tuple (obj, is_new): obj is the Empty object, is_new indicates whether it was created fresh.
    """
    return _layer3_get_or_create_empty(
        name,
        display_type,
        display_size,
        parent,
        collection,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        verify_transaction_wrong_type_object_ownership=_verify_transaction_wrong_type_object_ownership,
        authorized_unlink_object_from_collection=_authorized_unlink_object_from_collection,
        authorized_link_object_to_collection=_authorized_link_object_to_collection,
        authorized_assign_object_parent=_authorized_assign_object_parent,
        trigger_fault_injection=_trigger_fault_injection,
        matrix_cls=Matrix,
    )


def setup_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    initial_influence: float = 0.0,
) -> Dict[str, bpy.types.Object]:
    """Configure native Blender two-bone arm IK chains, elbow pole targets, and hand orientation controls.

    This function is strictly idempotent:
    - Preserves existing controller objects, parents, matrices, positions, orientations, and rotation modes.
    - Preserves existing constraint instances, configurations, and active influences.
    - Only initializes neutral rest positions when creating brand new controllers.
    - Only sets initial_influence when creating brand new constraints.
    - Only applies pre-bend hints when initializing a previously unconstrained arm.

    Args:
        armature_obj: Optional CharacterArmature object.
        initial_influence: Initial constraint influence in [0.0, 1.0]. Defaults to 0.0 (FK mode).

    Returns:
        Dict mapping controller names ('HandIK.L', 'HandIK.R', 'ElbowPole.L', 'ElbowPole.R')
        to their Empty objects.
    """
    return _layer4_setup_arm_ik(
        armature_obj,
        initial_influence,
        arm_rig_transaction=_arm_rig_transaction,
        assert_arm_rig_cleanup_gate=_assert_arm_rig_cleanup_gate,
        assert_arm_rig_failed_isolation_gate=_assert_arm_rig_failed_isolation_gate,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        armature_isolation_state=_ArmatureIsolationState,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        verify_transaction_wrong_type_object_ownership=_verify_transaction_wrong_type_object_ownership,
        ensure_character_collection=_ensure_character_collection,
        get_or_create_empty=_get_or_create_empty,
        authorized_create_constraint=_authorized_create_constraint,
        authorized_assign_constraint_targets=_authorized_assign_constraint_targets,
        trigger_fault_injection=_trigger_fault_injection,
        depsgraph_update=_depsgraph_update,
        uuid4=uuid.uuid4,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        shoulder_x_offset=SHOULDER_X_OFFSET,
        wrist_rest_z=WRIST_REST_Z,
        elbow_rest_z=ELBOW_REST_Z,
        default_pole_outward_offset=DEFAULT_POLE_OUTWARD_OFFSET,
        default_pole_backward_offset=DEFAULT_POLE_BACKWARD_OFFSET,
    )


def set_arm_ik_influence(
    armature_obj: Optional[bpy.types.Object] = None,
    side: str = "BOTH",
    influence: float = 1.0,
) -> None:
    """Set the IK and rotation constraint influence for one or both arms.

    Args:
        armature_obj: Optional CharacterArmature object.
        side: 'L', 'R', or 'BOTH'.
        influence: Influence value in [0.0, 1.0].
    """
    return _layer4_set_arm_ik_influence(
        armature_obj,
        side,
        influence,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        arm_rig_transaction=_arm_rig_transaction,
        trigger_fault_injection=_trigger_fault_injection,
        depsgraph_update=_depsgraph_update,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
    )


def reset_arm_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset both arms, empties, and constraint influences back to neutral rest (FK mode).

    Follows the Gate A-3 Transaction Atomicity Contract:
    - Phase 1: Resolves Armature and CharacterRoot, updates view layer.
    - Phase 2: Preflights effective parent transforms for all existing controllers on both sides (L and R)
      using compute_effective_parent_matrix() and validate_effective_parent_transform().
      If any preflight check fails, aborts immediately with ZERO scene writes on either side.
    - Phase 3: Enters unified _arm_rig_transaction(arm) context.
    - Phase 4: Executes bilateral reset with observable fault injection boundaries.
    - Phase 5: Synchronizes dependency graph and commits. Any write exception triggers atomic rollback.
    """
    return _layer4_reset_arm_ik(
        armature_obj,
        arm_rig_transaction=_arm_rig_transaction,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        trigger_fault_injection=_trigger_fault_injection,
        depsgraph_update=_depsgraph_update,
        compute_effective_parent_matrix=compute_effective_parent_matrix,
        validate_effective_parent_transform=validate_effective_parent_transform,
        world_to_local_position=world_to_local_position,
        apply_target_rotation=apply_target_rotation,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        shoulder_x_offset=SHOULDER_X_OFFSET,
        wrist_rest_z=WRIST_REST_Z,
        elbow_rest_z=ELBOW_REST_Z,
        default_pole_outward_offset=DEFAULT_POLE_OUTWARD_OFFSET,
        default_pole_backward_offset=DEFAULT_POLE_BACKWARD_OFFSET,
    )


def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    return _layer4_get_arm_ik_state(
        armature_obj,
        side,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        depsgraph_update=_depsgraph_update,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
    )


def _preflight_arm_ik_parent_transforms(
    arm: bpy.types.Object,
    valid_side: str,
    root_obj: Optional[bpy.types.Object],
) -> Tuple[bool, Matrix, Matrix]:
    """Preflight check effective parent transform domains before any scene mutation (Task 10-B-2 & 10-B-3).

    Inspects existing and anticipated arm IK controllers without writing to the scene.
    A controller is valid if and only if the object exists and its type is 'EMPTY'.
    If any controller on valid_side is missing or not an EMPTY, setup_arm_ik() will be required.

    Preflight rules:
    - Case A: Existing object is an EMPTY -> compute actual effective parent matrix.
    - Case B: Object does not exist -> compute expected effective parent matrix (root_obj @ Identity).
    - Case C: Object exists but type != 'EMPTY' -> must be a verified transaction-owned controller (F14-05);
      unowned non-EMPTY objects are rejected with EXTERNAL_CONTROLLER_NAME_CONFLICT before scene writes.

    Returns:
        (needs_auto_init, eff_ik_mat, eff_pole_mat)
    """
    return _layer4_preflight_arm_ik_parent_transforms(
        arm,
        valid_side,
        root_obj,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        verify_transaction_wrong_type_object_ownership=_verify_transaction_wrong_type_object_ownership,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        compute_effective_parent_matrix=compute_effective_parent_matrix,
        validate_effective_parent_transform=validate_effective_parent_transform,
    )


def set_hand_ik_target(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    world_xyz: Tuple[float, float, float],
    hand_rotation_deg: Optional[Tuple[float, float, float]] = None,
    pole_world_xyz: Optional[Tuple[float, float, float]] = None,
    clamp_reach: bool = True,
    influence: float = 1.0,
) -> dict:
    """Set the left ('L') or right ('R') hand IK target in world coordinates.

    Follows the 10-A, 10-B-1, and 10-B-2 Pre-validation and Zero-Side-Effect Contracts:
    - Phase A: Validates all user inputs strictly before any scene access or mutation.
    - Phase B: Preflights dependency graph (view_layer.update()) and validates effective
      parent transforms of existing and anticipated controllers before auto-initialization.
    - Phase C: Invokes setup_arm_ik() only after Phase B validation succeeds with zero mutation.
    - Phase D: Computes targets, checks finite derived coordinates, and commits transforms/influences.
    - HandIK and ElbowPole transforms are resolved independently using their respective M_eff.
    - Preserves controller active rotation_mode (Euler modes, QUATERNION, AXIS_ANGLE).
    - Rejects non-conformal transforms (shears, non-uniform scaling, reflections, singularities).
    - Preserves default neutral orientation matching CharacterRoot when hand_rotation_deg is None.

    Args:
        armature_obj: Optional CharacterArmature object.
        side: Arm side, 'L' or 'R'.
        world_xyz: Desired wrist position in world coordinates (meters).
        hand_rotation_deg: Desired hand 3D Euler orientation in world coordinates (degrees, 'XYZ').
        pole_world_xyz: Optional explicit elbow pole target in world coordinates.
        clamp_reach: If True, out-of-reach targets are safely projected onto the sphere of radius
            `MAX_ARM_REACH` (or `MIN_ARM_REACH`) centered at the shoulder. If False, target is
            unclamped (bone lengths are still strictly preserved via use_stretch=False).
        influence: Constraint influence to set on ArmIK and HandRotation in [0.0, 1.0]. Defaults to 1.0.

    Returns:
        dict containing state information including requested/applied positions, target error,
        rotation error, reachability flag, and clamping status.
    """
    return _layer4_set_hand_ik_target(
        armature_obj,
        side,
        world_xyz,
        hand_rotation_deg,
        pole_world_xyz,
        clamp_reach,
        influence,
        preflight_arm_ik_parent_transforms=_preflight_arm_ik_parent_transforms,
        setup_arm_ik=setup_arm_ik,
        get_arm_ik_state=get_arm_ik_state,
        arm_rig_transaction=_arm_rig_transaction,
        require_existing_arm_ik_controller_ownership=_require_existing_arm_ik_controller_ownership,
        trigger_fault_injection=_trigger_fault_injection,
        depsgraph_update=_depsgraph_update,
        update_arm_ik_depsgraph=_update_arm_ik_depsgraph,
        world_to_local_position=world_to_local_position,
        world_to_local_rotation_quaternion=world_to_local_rotation_quaternion,
        apply_target_rotation=apply_target_rotation,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        min_arm_reach=MIN_ARM_REACH,
        max_arm_reach=MAX_ARM_REACH,
        default_pole_outward_offset=DEFAULT_POLE_OUTWARD_OFFSET,
        default_pole_backward_offset=DEFAULT_POLE_BACKWARD_OFFSET,
    )
