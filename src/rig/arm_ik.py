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
    _admit_outermost_arm_rig_transaction as _layer1_admit_outermost_arm_rig_transaction,
    _assert_arm_rig_cleanup_gate as _layer1_assert_arm_rig_cleanup_gate,
    _assert_arm_rig_failed_isolation_gate as _layer1_assert_arm_rig_failed_isolation_gate,
    _capture_transaction_entry_fingerprint as _layer1_capture_transaction_entry_fingerprint,
    _commit_arm_rig_transaction as _layer1_commit_arm_rig_transaction,
    _establish_outermost_arm_rig_transaction as _layer1_establish_outermost_arm_rig_transaction,
    _identity_failure_is_uncertain,
    _release_active_arm_rig_transaction as _layer1_release_active_arm_rig_transaction,
    _safe_object_name,
    _snapshot_and_activate_transaction as _layer1_snapshot_and_activate_transaction,
)
from src.scene_transaction_integrity.layer2 import (
    ArmatureSessionIdentityRecord,
    _ACTIVE_TRANSACTION_STACK,
    _ARCHIVED_FAILED_D_TOMBSTONES,
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
    _initialize_arm_rig_transaction_context as _layer2_initialize_arm_rig_transaction_context,
    _prepare_relationship_mutation as _layer2_prepare_relationship_mutation,
    _record_failed_a_audit,
    _register_created_collection as _layer2_register_created_collection,
    _register_created_collection_link as _layer2_register_created_collection_link,
    _register_created_constraint as _layer2_register_created_constraint,
    _register_created_controller as _layer2_register_created_controller,
    _safe_object_pointer,
    _update_relationship_mutation_state as _layer2_update_relationship_mutation_state,
    _verify_armature_session_identity_record as _layer2_verify_armature_session_identity_record,
    ensure_armature_session_identity as _layer2_ensure_armature_session_identity,
)
from src.scene_transaction_integrity.layer3 import (
    ARM_IK_CONSTRAINT_NAMES,
    ExternalControllerNameConflictError,
    _TARGET_UNSET,
    _apply_single_constraint_target_unit as _layer3_apply_single_constraint_target_unit,
    _authorized_assign_constraint_targets as _layer3_authorized_assign_constraint_targets,
    _authorized_assign_object_parent as _layer3_authorized_assign_object_parent,
    _authorized_create_constraint as _layer3_authorized_create_constraint,
    _authorized_link_child_collection as _layer3_authorized_link_child_collection,
    _authorized_link_object_to_collection as _layer3_authorized_link_object_to_collection,
    _classify_constraint_target_pair_effect as _layer3_classify_constraint_target_pair_effect,
    _controller_constraint_binding_proven,
    _controller_is_borrowed_by_other_armature as _layer3_controller_is_borrowed_by_other_armature,
    _controller_role_for_name as _layer3_controller_role_for_name,
    _ensure_character_collection as _layer3_ensure_character_collection,
    _find_collection_by_name,
    _find_live_collection_by_identity as _layer3_find_live_collection_by_identity,
    _find_live_object_by_identity,
    _get_or_create_empty as _layer3_get_or_create_empty,
    _is_child_collection_linked_by_identity,
    _is_collection_descendant_of,
    _is_object_linked_to_collection_by_identity,
    _matrix_equals,
    _require_collection_child_relationship_ownership as _layer3_require_collection_child_relationship_ownership,
    _require_existing_arm_ik_controller_ownership as _layer3_require_existing_arm_ik_controller_ownership,
    _verify_controller_object_transaction_authority as _layer3_verify_controller_object_transaction_authority,
    _verify_transaction_wrong_type_object_ownership as _layer3_verify_transaction_wrong_type_object_ownership,
)
from src.scene_transaction_integrity.layer4 import (
    _apply_arm_ik_prebend_hint,
    _apply_arm_ik_prebend_hint_side,
    _preflight_arm_ik_parent_transforms as _layer4_preflight_arm_ik_parent_transforms,
    _resolve_armature,
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
    _snapshot_arm_rig_state as _layer5_snapshot_arm_rig_state,
)
from src.scene_transaction_integrity.layer6 import (
    _CleanupOutcome,
    _CleanupResult,
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
    if (not _ACTIVE_TRANSACTION_STACK
            or _ACTIVE_TRANSACTION_STACK[-1] is not active_tx
            or active_tx.state != _ArmRigTransactionState.ACTIVE):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: transaction not ACTIVE")
    if (type(expected_ptr) is not int or expected_ptr <= 0
            or not isinstance(active_tx.entry_collection_ptrs, (set, frozenset))
            or expected_ptr in active_tx.entry_collection_ptrs):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: creation baseline invalid")
    registry = active_tx.created_collections
    receipts = active_tx._collection_creation_receipts
    if (not isinstance(registry, list) or not isinstance(receipts, dict)
            or any(not isinstance(rec, dict) for rec in registry)):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: registry malformed")
    try:
        ptr = int(col.as_pointer())
        parent_ptr = int(initial_parent.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: identity unreadable") from exc
    if (ptr != expected_ptr or parent_ptr <= 0
            or _find_live_collection_by_identity(col, expected_ptr) is None
            or _find_live_collection_by_identity(initial_parent, parent_ptr) is None):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: original identity lost")

    records = [rec for rec in registry if rec.get("col_ptr") == expected_ptr]
    receipt = receipts.get(expected_ptr)
    if records or receipt is not None:
        # The receipt+registry pair is authoritative after successful
        # registration. Let the enclosing transaction remove it exactly once.
        if (len(records) != 1 or not isinstance(receipt, tuple) or len(receipt) != 5
                or records[0].get("col_ref") != col
                or records[0].get("initial_parent") != initial_parent
                or records[0].get("initial_parent_ptr") != parent_ptr
                or receipt[0] != col or receipt[1] != initial_parent
                or receipt[2] != active_tx.session_id
                or receipt[3] != active_tx.tx_id
                or receipt[4] is not active_tx._collection_receipt_seal):
            raise RuntimeError(
                "COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: partial or mismatched registration"
            )
        return

    # This is the small gap between bpy.data.collections.new() and successful
    # registration. Only the exact unlinked newly returned ID may be removed.
    if (not any(c == col and int(c.as_pointer()) == expected_ptr
                for c in bpy.data.collections)
            or int(col.users) != 0
            or len(col.objects) != 0
            or len(col.children) != 0):
        raise RuntimeError(
            "COLLECTION_CREATION_CLEANUP_REFUSED: unregistered Collection has external dependencies"
        )
    # Avoid removing a Collection that became a child of some other parent,
    # even if a mocked/inconsistent Blender user counter erroneously says zero.
    for parent in bpy.data.collections:
        if parent != col and _is_child_collection_linked_by_identity(parent, col, expected_ptr):
            raise RuntimeError("COLLECTION_CREATION_CLEANUP_REFUSED: Collection gained a parent")
    for scene in bpy.data.scenes:
        if _is_child_collection_linked_by_identity(scene.collection, col, expected_ptr):
            raise RuntimeError("COLLECTION_CREATION_CLEANUP_REFUSED: Collection gained a scene parent")

    try:
        bpy.data.collections.remove(col)
    except BaseException as exc:
        raise RuntimeError(
            f"COLLECTION_CREATION_CLEANUP_REMOVE_FAILED: ptr={expected_ptr}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if _find_live_collection_by_identity(col, expected_ptr) is not None:
        raise RuntimeError(
            f"COLLECTION_CREATION_CLEANUP_REMOVE_UNVERIFIED: ptr={expected_ptr} still live"
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
    for session_id, rec in list(_MANAGED_ARMATURE_IDENTITIES.items()):
        if rec.isolation_state == _ArmatureIsolationState.ARCHIVED_RETIRED:
            continue
        obj_liveness = _check_original_object_liveness(rec)
        if obj_liveness["status"] == "UNKNOWN":
            # Cannot prove death or liveness; preserve existing isolation state without escalation
            continue
        ver = _verify_armature_session_identity_record(rec, candidate_arm=None)
        # Only escalate to TOMBSTONED_FAILED_D if object is genuinely ABSENT
        # or if object is ALIVE but data block identity has been invalidated/replaced (Condition 7 failed).
        is_dead = (obj_liveness["status"] == "ABSENT")
        is_data_invalidated = (
            obj_liveness["status"] == "ALIVE"
            and not ver.get("identity_verification_uncertain", False)
            and not ver["checks"].get("c7_data_valid_and_pointer_matches", False)
        )
        if is_dead or is_data_invalidated:
            iso_rec = _ISOLATED_FAILED_ARMATURES.get(session_id)
            if iso_rec is not None and rec.isolation_state != _ArmatureIsolationState.TOMBSTONED_FAILED_D:
                rec.isolation_state = _ArmatureIsolationState.TOMBSTONED_FAILED_D
                rec.lifecycle_stage = "TOMBSTONED_FAILED_D"
                tombstone = {
                    "registry_session_id": session_id,
                    "registration_pointer": rec.registration_pointer,
                    "original_data_pointer": rec.original_data_pointer,
                    "registered_name_snapshot": rec.registered_name_snapshot,
                    "failure_class": _FailedTransactionClass.FAILED_D.value,
                    "isolation_state": _ArmatureIsolationState.TOMBSTONED_FAILED_D.value,
                    "retirement_state": "ACTIVE_TOMBSTONE",
                    "reasons": ver["reasons"],
                }
                rec.tombstone_record = tombstone
                iso_rec["failure_class"] = _FailedTransactionClass.FAILED_D.value
                iso_rec["isolation_state"] = _ArmatureIsolationState.TOMBSTONED_FAILED_D.value
                iso_rec["tombstone_record"] = tombstone


def ensure_armature_session_identity(arm: bpy.types.Object) -> ArmatureSessionIdentityRecord:
    """Layer 2: Resolve existing verified ArmatureSessionIdentityRecord or register a new session identity."""
    return _layer2_ensure_armature_session_identity(
        arm,
        sweep_dead_managed_armature_identities=_sweep_dead_managed_armature_identities,
    )


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
    f_class = (
        failure_class
        if isinstance(failure_class, _FailedTransactionClass)
        else _FailedTransactionClass(failure_class)
    )
    tx.failure_class = f_class.value

    if f_class == _FailedTransactionClass.FAILED_A:
        return _record_failed_a_audit(
            session_rec=session_rec,
            tx_id=tx.tx_id,
            f_class=f_class,
            primary_exception=primary_exception,
        )

    if f_class == _FailedTransactionClass.FAILED_B:
        iso_state = _ArmatureIsolationState.ISOLATED_FAILED_B
    elif f_class == _FailedTransactionClass.FAILED_C:
        iso_state = _ArmatureIsolationState.ISOLATED_FAILED_C
    elif f_class == _FailedTransactionClass.FAILED_D:
        iso_state = _ArmatureIsolationState.TOMBSTONED_FAILED_D
    else:
        raise RuntimeError(f"Unsupported failure class for isolation: {f_class}")

    session_rec.isolation_state = iso_state
    if f_class == _FailedTransactionClass.FAILED_D:
        session_rec.liveness_status = _ArmatureLivenessStatus.INVALIDATED_DEAD
        obj_liveness = _check_original_object_liveness(session_rec)
        if obj_liveness["status"] == "ALIVE":
            session_rec.in_live_blender_collection = True
        elif obj_liveness["status"] == "ABSENT":
            session_rec.in_live_blender_collection = False
        session_rec.lifecycle_stage = "TOMBSTONED_FAILED_D"

    snapshot_trusted = bool(
        tx.snapshot is not None
        and f_class in (_FailedTransactionClass.FAILED_B, _FailedTransactionClass.FAILED_C)
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
        if r.get("operation_state") == _RelationshipOperationState.RECOVERY_UNCERTAIN
    ]

    tombstone_rec: Optional[Dict[str, Any]] = None
    if f_class == _FailedTransactionClass.FAILED_D:
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
    _ISOLATED_FAILED_ARMATURES[session_rec.registry_session_id] = iso_record
    tx.isolation_record = iso_record
    return iso_record


_COORDINATOR_AUTHORIZATION_GRANTS: Dict[str, Dict[str, Any]] = {}

# Coordinator grants are process-local, ephemeral capabilities, not long-lived
# isolation records. Expiration is evaluated lazily at issuance/consumption;
# expired or superseded capabilities can never be used to clear isolation.
_COORDINATOR_GRANT_TTL_SECONDS: float = 60.0


def _coordinator_reap_stale_authorization_grants() -> None:
    """Revoke expired, malformed, or provenance-stale grants without touching FAILED isolation."""
    now = time.monotonic()
    for grant_id, grant in tuple(_COORDINATOR_AUTHORIZATION_GRANTS.items()):
        if not isinstance(grant, dict):
            _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)
            continue
        issued = grant.get("issued_monotonic")
        expires = grant.get("expires_monotonic")
        session_id = grant.get("registry_session_id")
        session = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
        isolation = _ISOLATED_FAILED_ARMATURES.get(session_id)
        invalid_time = (
            type(issued) not in (float, int)
            or type(expires) not in (float, int)
            or not (math.isfinite(issued) and math.isfinite(expires))
            or issued > now or expires <= now
            or expires <= issued
            or expires - issued > _COORDINATOR_GRANT_TTL_SECONDS + 1e-6
        )
        stale_binding = (
            session is None or isolation is None
            or session.registry_session_id != session_id
            or isolation.get("registry_session_id") != session_id
            or isolation.get("transaction_id") != grant.get("transaction_id")
            or isolation.get("failure_class") != grant.get("failure_class")
            or session.isolation_state.value != grant.get("current_isolation_state")
            or isolation.get("isolation_state") != grant.get("current_isolation_state")
        )
        if (
            invalid_time or stale_binding or grant.get("consumed") is not False
            or grant.get("grant_id") != grant_id
            or not isinstance(grant.get("capability_nonce"), str)
            or not grant.get("capability_nonce")
        ):
            _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)


def _coordinator_revoke_session_authorization_grants(session_id: str) -> None:
    """Invalidate all older grants for a session after a new issue or successful transition."""
    for grant_id, grant in tuple(_COORDINATOR_AUTHORIZATION_GRANTS.items()):
        if isinstance(grant, dict) and grant.get("registry_session_id") == session_id:
            _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)



def _issue_coordinator_authorization_grant(
    session_id: str,
    transition_action: str = "CLEAR_TO_NONE",
    arm: Optional[bpy.types.Object] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Issue a single-use internal authorization grant binding verified Layer 5 recovery evidence.

    Execution order:
    1. Read current session from _MANAGED_ARMATURE_IDENTITIES.
    2. Read current isolation record from _ISOLATED_FAILED_ARMATURES.
    3. Confirm both point to the same session.
    4. Check requested transition_action in ("CLEAR_TO_NONE", "ARCHIVE_TOMBSTONE").
    5. Call Layer 5 to execute real-time verification (verify_armature_deisolation_evidence or _verify_dead_armature_tombstone_retirement_evidence).
    6. Verify that verification evidence matches registry fields strictly.
    7. Generate single-use grant binding grant_id, session, tx_id, failure_class, isolation_state, action.
    8. Register grant in _COORDINATOR_AUTHORIZATION_GRANTS.
    9. Return grant.
    """
    session_rec = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(session_id)
    if session_rec is None:
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: session '{session_id}' not found in _MANAGED_ARMATURE_IDENTITIES")
    if iso_rec is None:
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: session '{session_id}' not found in _ISOLATED_FAILED_ARMATURES")

    if session_rec.registry_session_id != session_id or iso_rec.get("registry_session_id") != session_id:
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: registry session ID mismatch for '{session_id}'")

    if transition_action not in ("CLEAR_TO_NONE", "ARCHIVE_TOMBSTONE"):
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: unsupported transition action {transition_action!r}")

    tx_id = iso_rec.get("transaction_id")
    failure_class = iso_rec.get("failure_class")
    current_iso_state = session_rec.isolation_state.value

    if transition_action == "CLEAR_TO_NONE":
        target_arm = arm if arm is not None else session_rec.original_blender_ref
        evidence = verify_armature_deisolation_evidence(arm=target_arm, session_id=session_id)

        if not evidence.get("can_deisolate", False) or evidence.get("status") != "RECOVERY_VERIFIED":
            err_reasons = "; ".join(evidence.get("reasons", [])) or f"status is {evidence.get('status')}"
            raise RuntimeError(f"Cannot issue Coordinator authorization grant: recovery verification failed: {err_reasons}")

        if evidence.get("registry_session_id") != session_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence registry_session_id mismatch")
        if evidence.get("transaction_id") != tx_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence transaction_id mismatch")
        if evidence.get("failure_class") != failure_class:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence failure_class mismatch")
        if evidence.get("isolation_state") != current_iso_state:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence isolation_state mismatch")

        evidence_status = evidence.get("status", "RECOVERY_VERIFIED")

    elif transition_action == "ARCHIVE_TOMBSTONE":
        evidence = _verify_dead_armature_tombstone_retirement_evidence(session_id=session_id)

        if not evidence.get("can_retire", False) or evidence.get("status") != "TOMBSTONE_RETIREMENT_VERIFIED":
            err_reasons = "; ".join(evidence.get("reasons", [])) or f"status is {evidence.get('status')}"
            raise RuntimeError(f"Cannot issue Coordinator authorization grant: tombstone retirement verification failed: {err_reasons}")

        if failure_class != _FailedTransactionClass.FAILED_D.value or current_iso_state != _ArmatureIsolationState.TOMBSTONED_FAILED_D.value:
            raise RuntimeError(f"Cannot issue Coordinator authorization grant: session '{session_id}' is not an active FAILED-D tombstone")

        if evidence.get("registry_session_id") != session_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence registry_session_id mismatch")
        if evidence.get("transaction_id") != tx_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence transaction_id mismatch")

        evidence_status = evidence.get("status", "TOMBSTONE_RETIREMENT_VERIFIED")

    # Only the latest verified capability for a session remains active.
    # This does not clear any FAILED isolation or modify Blender resources.
    _coordinator_reap_stale_authorization_grants()
    _coordinator_revoke_session_authorization_grants(session_id)
    issued_monotonic = time.monotonic()
    grant_id = f"grant_{uuid.uuid4().hex}"
    grant = {
        "grant_id": grant_id,
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "current_isolation_state": current_iso_state,
        "transition_action": transition_action,
        "evidence_status": evidence_status,
        "capability_nonce": uuid.uuid4().hex,
        "issued_monotonic": issued_monotonic,
        "expires_monotonic": issued_monotonic + _COORDINATOR_GRANT_TTL_SECONDS,
        "consumed": False,
        "created_at": time.time(),
    }
    # A caller receives a separate dictionary; mutating the returned grant
    # cannot rewrite the Coordinator's authoritative capability record.
    _COORDINATOR_AUTHORIZATION_GRANTS[grant_id] = dict(grant)
    return grant


def _clear_coordinator_authorization_grants() -> None:
    """Clear active Coordinator authorization grants (test fixture cleanup)."""
    _COORDINATOR_AUTHORIZATION_GRANTS.clear()


def _clear_or_retire_failure_isolation_by_coordinator(
    session_id: str,
    action: str,
    reason: str,
    authorization_grant: Optional[Dict[str, Any]] = None,
    verification_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer 2: Clear FAILED-B/C isolation or archive FAILED-D tombstone exclusively for Layer 1 Coordinator."""
    if authorization_grant is None:
        raise RuntimeError(
            f"Layer 2 rejected {'de-isolation' if action == 'CLEAR_TO_NONE' else 'tombstone retirement'}: "
            "authorization_grant is required; verification_evidence is not authorization"
        )
    grant_candidate = authorization_grant
    session_rec = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(session_id)
    if session_rec is None or iso_rec is None:
        raise RuntimeError(f"Cannot modify isolation state: session {session_id} not found in active isolation registry")

    action_label = "de-isolation" if action == "CLEAR_TO_NONE" else "tombstone retirement"

    # Audit & validate Coordinator single-use authorization grant
    if not isinstance(grant_candidate, dict):
        raise RuntimeError(f"Layer 2 rejected {action_label}: authorization_grant must be a valid dictionary")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError(f"Layer 2 rejected {action_label}: non-empty reason is required")
    grant_id = grant_candidate.get("grant_id")
    _coordinator_reap_stale_authorization_grants()
    if not grant_id or grant_id not in _COORDINATOR_AUTHORIZATION_GRANTS:
        raise RuntimeError(f"Layer 2 rejected {action_label}: invalid or missing Coordinator authorization grant")

    registered_grant = _COORDINATOR_AUTHORIZATION_GRANTS[grant_id]
    if registered_grant.get("consumed", False):
        raise RuntimeError(f"Layer 2 rejected {action_label}: Coordinator authorization grant has already been consumed")
    if registered_grant.get("registry_session_id") != session_id:
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant session mismatch "
            f"('{registered_grant.get('registry_session_id')}' != '{session_id}')"
        )
    if registered_grant.get("transition_action") != action:
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant action mismatch "
            f"('{registered_grant.get('transition_action')}' != '{action}')"
        )
    if registered_grant.get("transaction_id") != iso_rec.get("transaction_id"):
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant transaction ID mismatch "
            f"('{registered_grant.get('transaction_id')}' != '{iso_rec.get('transaction_id')}')"
        )
    if registered_grant.get("failure_class") != iso_rec.get("failure_class"):
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant failure class mismatch "
            f"('{registered_grant.get('failure_class')}' != '{iso_rec.get('failure_class')}')"
        )
    if registered_grant.get("current_isolation_state") != session_rec.isolation_state.value:
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant isolation state mismatch "
            f"('{registered_grant.get('current_isolation_state')}' != '{session_rec.isolation_state.value}')"
        )

    # Authenticate the *presented* capability against the independent
    # Coordinator-owned record, not merely an attacker-supplied grant_id.
    if grant_candidate is registered_grant:
        raise RuntimeError(f"Layer 2 rejected {action_label}: grant registry record is not independently owned")
    bound_fields = (
        "grant_id", "registry_session_id", "transaction_id", "failure_class",
        "current_isolation_state", "transition_action", "evidence_status",
        "capability_nonce", "issued_monotonic", "expires_monotonic", "created_at",
    )
    if any(grant_candidate.get(field) != registered_grant.get(field) for field in bound_fields):
        raise RuntimeError(f"Layer 2 rejected {action_label}: presented grant binding mismatch")
    if grant_candidate.get("consumed") is not False:
        raise RuntimeError(f"Layer 2 rejected {action_label}: presented grant is already consumed")
    issued = registered_grant.get("issued_monotonic")
    expires = registered_grant.get("expires_monotonic")
    now = time.monotonic()
    if (
        type(issued) not in (float, int)
        or type(expires) not in (float, int)
        or not (math.isfinite(issued) and math.isfinite(expires))
        or now < issued or now >= expires
        or expires <= issued
        or expires - issued > _COORDINATOR_GRANT_TTL_SECONDS + 1e-6
    ):
        _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)
        raise RuntimeError(f"Layer 2 rejected {action_label}: authorization grant expired or invalid")

    # Evidence is not a permanent permission. Re-evaluate it immediately
    # before the FAILED-isolation state transition (TOCTOU defense).
    if action == "CLEAR_TO_NONE":
        latest_evidence = verify_armature_deisolation_evidence(
            arm=session_rec.original_blender_ref, session_id=session_id,
        )
        evidence_ok = (
            latest_evidence.get("can_deisolate") is True
            and latest_evidence.get("status") == "RECOVERY_VERIFIED"
        )
    elif action == "ARCHIVE_TOMBSTONE":
        latest_evidence = _verify_dead_armature_tombstone_retirement_evidence(session_id)
        evidence_ok = (
            latest_evidence.get("can_retire") is True
            and latest_evidence.get("status") == "TOMBSTONE_RETIREMENT_VERIFIED"
        )
    else:
        raise RuntimeError(f"Layer 2 rejected {action_label}: unsupported transition action")
    evidence_ok = evidence_ok and (
        latest_evidence.get("registry_session_id") == session_id
        and latest_evidence.get("transaction_id") == registered_grant.get("transaction_id")
        and latest_evidence.get("failure_class") == registered_grant.get("failure_class")
        and latest_evidence.get("isolation_state") == registered_grant.get("current_isolation_state")
        and latest_evidence.get("status") == registered_grant.get("evidence_status")
    )
    if not evidence_ok:
        _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: recovery evidence no longer verified "
            f"({latest_evidence.get('status')}: {latest_evidence.get('reasons', [])})"
        )
    # Revalidation may update liveness records; check original isolation
    # identity and state once more before consuming the capability.
    if (
        _MANAGED_ARMATURE_IDENTITIES.get(session_id) is not session_rec
        or _ISOLATED_FAILED_ARMATURES.get(session_id) is not iso_rec
        or iso_rec.get("registry_session_id") != session_id
        or iso_rec.get("transaction_id") != registered_grant.get("transaction_id")
        or iso_rec.get("failure_class") != registered_grant.get("failure_class")
        or session_rec.isolation_state.value != registered_grant.get("current_isolation_state")
        or iso_rec.get("isolation_state") != registered_grant.get("current_isolation_state")
    ):
        _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)
        raise RuntimeError(f"Layer 2 rejected {action_label}: isolation provenance changed during revalidation")

    # Real-time verification can be slow. Recheck the deadline immediately
    # before consumption rather than allowing a just-expired grant to pass.
    if time.monotonic() >= expires:
        _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)
        raise RuntimeError(f"Layer 2 rejected {action_label}: authorization grant expired during evidence verification")

    # Atomic single-use consumption before irreversible isolation transition;
    # replay cannot succeed even when the transition raises afterwards.
    registered_grant["consumed"] = True
    _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)
    grant_candidate["consumed"] = True

    if action == "CLEAR_TO_NONE":
        if session_rec.isolation_state == _ArmatureIsolationState.TOMBSTONED_FAILED_D:
            raise RuntimeError("Layer 2 rejected de-isolation: TOMBSTONED_FAILED_D cannot return to active status")
        previous_state = session_rec.isolation_state.value
        session_rec.isolation_state = _ArmatureIsolationState.NONE
        session_rec.lifecycle_stage = "NORMAL_TERMINAL"
        _ISOLATED_FAILED_ARMATURES.pop(session_id, None)
        _coordinator_revoke_session_authorization_grants(session_id)
        return {
            "registry_session_id": session_id,
            "previous_isolation_state": previous_state,
            "new_isolation_state": _ArmatureIsolationState.NONE.value,
            "action": "CLEAR_TO_NONE",
            "reason": reason,
            "grant_id": grant_id,
        }
    elif action == "ARCHIVE_TOMBSTONE":
        if session_rec.isolation_state != _ArmatureIsolationState.TOMBSTONED_FAILED_D:
            raise RuntimeError(
                f"Layer 2 rejected tombstone retirement: session {session_id} is in {session_rec.isolation_state}, "
                "expected TOMBSTONED_FAILED_D"
            )
        previous_state = session_rec.isolation_state.value
        session_rec.isolation_state = _ArmatureIsolationState.ARCHIVED_RETIRED
        session_rec.lifecycle_stage = "ARCHIVED_RETIRED"
        iso_rec["isolation_state"] = _ArmatureIsolationState.ARCHIVED_RETIRED.value
        if session_rec.tombstone_record is not None:
            session_rec.tombstone_record["isolation_state"] = _ArmatureIsolationState.ARCHIVED_RETIRED.value
            session_rec.tombstone_record["retirement_state"] = "ARCHIVED_RETIRED"
            session_rec.tombstone_record["retirement_reason"] = reason
        _ISOLATED_FAILED_ARMATURES.pop(session_id, None)
        _ARCHIVED_FAILED_D_TOMBSTONES[session_id] = iso_rec
        _coordinator_revoke_session_authorization_grants(session_id)
        return {
            "registry_session_id": session_id,
            "previous_isolation_state": previous_state,
            "new_isolation_state": _ArmatureIsolationState.ARCHIVED_RETIRED.value,
            "action": "ARCHIVE_TOMBSTONE",
            "reason": reason,
            "grant_id": grant_id,
        }
    else:
        raise RuntimeError(f"Unsupported Layer 2 isolation transition action: {action!r}")


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


_DEPSGRAPH_UPDATER: Callable[[], None] = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None


def _set_test_depsgraph_updater(updater: Optional[Callable[[], None]]) -> None:
    """Private test hook to replace or wrap depsgraph update execution at the boundary."""
    global _DEPSGRAPH_UPDATER
    if updater is None:
        _DEPSGRAPH_UPDATER = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None
    else:
        _DEPSGRAPH_UPDATER = updater


def _clear_test_depsgraph_updater() -> None:
    """Clear private test depsgraph updater hook."""
    global _DEPSGRAPH_UPDATER
    _DEPSGRAPH_UPDATER = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None


def _depsgraph_update() -> None:
    """Internal unified dependency graph update boundary."""
    _DEPSGRAPH_UPDATER()


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
    reasons: List[str] = []

    # 1. Verification of Transaction Execution Phase
    if getattr(tx, "pre_write_integrity_compromised", False):
        extra = getattr(tx, "pre_write_integrity_reasons", [])
        reasons.extend(extra if extra else ["Transaction pre-write integrity explicitly marked compromised"])

    if tx.snapshot is not None:
        reasons.append("Transaction captured full snapshot; cannot be verified via pre-snapshot zero-mutation path")

    if tx.state not in (
        _ArmRigTransactionState.CREATED,
        _ArmRigTransactionState.SNAPSHOTTING,
        _ArmRigTransactionState.FAILED,
    ):
        reasons.append(
            f"Transaction reached post-snapshot execution state '{tx.state.value}'; "
            "cannot be verified as FAILED-A pre-write abort"
        )

    if (
        tx.created_controller_objects
        or tx.created_constraints
        or tx.created_collection_links
        or tx.prepared_relationship_mutations
        or tx.stashed_objects
        or tx.stashed_constraints
        or tx.created_collections
    ):
        reasons.append("Transaction recorded resource or relationship mutations before reaching ACTIVE")

    if pre_fp is None:
        reasons.append("Pre-snapshot structural fingerprint is missing")
        return {"is_verified": False, "reasons": reasons}

    try:
        post_fp = _capture_pre_snapshot_structural_fingerprint(arm)
    except BaseException as exc:
        reasons.append(f"Failed to capture post-exception structural fingerprint: {exc}")
        return {"is_verified": False, "reasons": reasons}

    # 2. A failed finiteness check is untrusted evidence, not a verified clean state.
    try:
        nonfinite = _has_nan_or_inf(pre_fp) or _has_nan_or_inf(post_fp)
    except BaseException as scan_exc:
        reasons.append(
            f"Pre-write fingerprint finiteness could not be verified: "
            f"{type(scan_exc).__name__}: {scan_exc}"
        )
    else:
        if nonfinite:
            reasons.append("Pre-write structural fingerprint contains NaN or Infinite floating point values")

    # 3. Check for missing bones
    if post_fp.get("total_pose_bone_count", 0) > 0:
        missing_bones = [
            b for b in _REQUIRED_ARM_IK_BONE_NAMES
            if b not in post_fp.get("present_arm_bones", ())
        ]
        if missing_bones:
            reasons.append(f"Required upper-limb pose bones missing: {missing_bones}")

    # 4. Compare every key in fingerprint for exact unrounded equality
    for key in (
        "arm_ptr",
        "arm_name",
        "data_ptr",
        "total_pose_bone_count",
        "present_arm_bones",
        "character_collection",
        "controllers",
        "pose_bones",
        "all_object_ptrs",
        "all_collection_ptrs",
    ):
        pre_val = pre_fp.get(key)
        post_val = post_fp.get(key)
        if pre_val != post_val:
            reasons.append(f"Pre-write state mutated during SNAPSHOTTING in field '{key}'")

    return {
        "is_verified": len(reasons) == 0,
        "reasons": reasons,
    }


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
    global _ACTIVE_TRANSACTION_STACK
    if active_tx is None and _ACTIVE_TRANSACTION_STACK:
        active_tx = _ACTIVE_TRANSACTION_STACK[-1]

    if active_tx is None:
        obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
        if _is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
            collection.objects.unlink(obj)
        return None

    col_ptr = collection.as_pointer() if hasattr(collection, "as_pointer") else None
    obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
    obj_name = getattr(obj, "name", "<unknown>")

    # 1. PREPARE
    already_linked = _is_object_linked_to_collection_by_identity(collection, obj, obj_ptr)
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=collection,
        target_reference=obj,
        original_relationship_state={
            "linked": already_linked,
            "category": category,
            "col_ptr": col_ptr,
            "obj_ptr": obj_ptr,
        },
        intended_mutation="COLLECTION_OBJECT_UNLINK",
    )

    _trigger_fault_injection(
        "relationship_unlink_after_prepare",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )

    if not already_linked:
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.NO_EFFECT,
        )
        return op_record

    # 2. APPLY
    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.APPLYING,
    )
    try:
        _trigger_fault_injection(
            "relationship_unlink_during_apply_before_c_api",
            {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
        )
        live_col = _find_live_collection_by_identity(collection, col_ptr)
        live_obj = _find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if live_col is None or live_obj is None:
            raise RuntimeError("Target object or collection identity invalid during unlink apply")

        live_col.objects.unlink(live_obj)

        _trigger_fault_injection(
            "relationship_unlink_during_apply_after_c_api",
            {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
        )
    except BaseException:
        check_col = _find_live_collection_by_identity(collection, col_ptr)
        check_obj = _find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if check_col is None or check_obj is None:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
        elif not _is_object_linked_to_collection_by_identity(check_col, check_obj, obj_ptr):
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.APPLIED_VERIFIED,
            )
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.NO_EFFECT,
            )
        raise

    if _is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection unlink apply did not take effect in RNA for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.APPLIED_VERIFIED,
    )

    # 3. CONFIRM
    _trigger_fault_injection(
        "relationship_unlink_before_confirm",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )
    confirm_col = _find_live_collection_by_identity(collection, col_ptr)
    confirm_obj = _find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
    if (
        confirm_col is None
        or confirm_obj is None
        or _is_object_linked_to_collection_by_identity(confirm_col, confirm_obj, obj_ptr)
    ):
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection unlink verification failed at CONFIRM stage for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.CONFIRMED,
    )
    return op_record


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
    global _ACTIVE_TRANSACTION_STACK
    if active_tx is None and _ACTIVE_TRANSACTION_STACK:
        active_tx = _ACTIVE_TRANSACTION_STACK[-1]

    if active_tx is None or active_tx.state != _ArmRigTransactionState.ACTIVE:
        raise RuntimeError("Collection child unlink requires an active transaction in ACTIVE state")

    p_ptr = parent_collection.as_pointer() if hasattr(parent_collection, "as_pointer") else None
    c_ptr = child_collection.as_pointer() if hasattr(child_collection, "as_pointer") else None

    live_parent = _find_live_collection_by_identity(parent_collection, p_ptr)
    live_child = _find_live_collection_by_identity(child_collection, c_ptr)
    if live_parent is None or live_child is None:
        raise RuntimeError("Parent or child collection identity invalid during child unlink")

    already_linked = _is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr)
    child_name = getattr(child_collection, "name", "<unknown>")
    if already_linked:
        _require_collection_child_relationship_ownership(
            parent_collection, child_collection, active_tx, unlink=True,
        )

    # 1. PREPARE
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=parent_collection,
        target_reference=child_collection,
        original_relationship_state={
            "linked": already_linked,
            "category": category,
            "parent_col_ref": parent_collection,
            "parent_col_ptr": p_ptr,
            "parent_col_name": parent_collection.name,
            "child_col_ref": child_collection,
            "child_col_ptr": c_ptr,
            "child_col_name": child_name,
        },
        intended_mutation="COLLECTION_CHILD_UNLINK",
    )
    op_record["parent_col_ref"] = parent_collection
    op_record["parent_col_ptr"] = p_ptr
    op_record["parent_col_name"] = parent_collection.name
    op_record["child_col_ref"] = child_collection
    op_record["child_col_ptr"] = c_ptr
    op_record["child_col_name"] = child_name
    op_record["category"] = category

    _trigger_fault_injection(
        "collection_child_unlink_after_prepare",
        {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
    )

    if not already_linked:
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.NO_EFFECT,
        )
        return op_record

    # 2. APPLY
    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.APPLYING,
    )

    try:
        _trigger_fault_injection(
            "collection_child_unlink_during_apply_before_c_api",
            {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
        )

        parent_collection.children.unlink(child_collection)

        _trigger_fault_injection(
            "collection_child_unlink_during_apply_after_c_api",
            {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
        )
    except BaseException:
        if not _is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.APPLIED_VERIFIED,
            )
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.NO_EFFECT,
            )
        raise

    if _is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection child unlink did not take effect in RNA for '{child_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.APPLIED_VERIFIED,
    )

    # 3. CONFIRM
    _trigger_fault_injection(
        "collection_child_unlink_before_confirm",
        {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
    )

    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.CONFIRMED,
    )
    return op_record


def _authorized_restore_relationship(
    active_tx: Optional[Any],
    snapshot: Optional[Dict[str, Any]],
    restoration_errors: List[str],
    mutation_type: Optional[str] = None,
) -> None:
    """Authoritatively revert and restore relationships via Layer 3 records."""
    if active_tx is None:
        return
    for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
        if mutation_type is None or op_record.get("intended_mutation") == mutation_type:
            _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)


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
    if (not _ACTIVE_TRANSACTION_STACK
            or _ACTIVE_TRANSACTION_STACK[-1] is not active_tx
            or active_tx.state != _ArmRigTransactionState.ACTIVE):
        raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: transaction not ACTIVE")
    if (type(expected_ptr) is not int or expected_ptr <= 0
            or type(pbone_ptr) is not int or pbone_ptr <= 0
            or not isinstance(before_ptrs, frozenset)
            or expected_ptr in before_ptrs):
        raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: creation baseline invalid")
    try:
        live_arm = active_tx.arm
        if (live_arm is None or live_arm.pose is None
                or live_arm.pose.bones.get(pbone.name) != pbone
                or int(pbone.as_pointer()) != pbone_ptr
                or int(con.as_pointer()) != expected_ptr):
            raise RuntimeError("original PoseBone/Constraint identity changed")
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: identity mismatch") from exc

    registry = active_tx.created_constraints
    if (not isinstance(registry, list)
            or any(not isinstance(rec, dict) for rec in registry)):
        raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: registry malformed")
    related = [rec for rec in registry
               if rec.get("con_ptr") == expected_ptr or rec.get("con_ref") == con]

    # [INTRODUCED 2026-11-16T18:15:00+08:00]
    # FUNCTION: _cleanup_failed_constraint_creation
    # PURPOSE: Enforce strict 8-tuple receipt validation on registered resources and revoke unregistered receipts upon verified compensation
    # REASON: Task 10-B fix-4, handle Window 1 and Window 2 creation failure compensation safely without phantom receipts
    receipts = getattr(active_tx, "_constraint_creation_receipts", {})
    if not isinstance(receipts, dict):
        raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: receipt ledger malformed")

    if related:
        # Once a complete registration exists, the enclosing transaction's
        # existing Layer-3 rollback exclusively owns destruction.
        if (len(related) != 1
                or related[0].get("con_ref") != con
                or related[0].get("con_ptr") != expected_ptr
                or related[0].get("pbone") != pbone
                or related[0].get("bone_name") != pbone.name):
            raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: partial/mismatched registration")
        if expected_ptr not in receipts:
            raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: registered constraint missing creation receipt")
        rc = receipts[expected_ptr]
        if not isinstance(rc, tuple) or len(rc) != 8:
            raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: creation receipt length must be exactly 8")
        rc_con, rc_con_ptr, rc_pbone, rc_pbone_ptr, rc_session_id, rc_tx_id, rc_seal, rc_before_ptrs = rc
        if (rc_con != con or rc_con_ptr != expected_ptr
                or rc_pbone != pbone or type(rc_pbone_ptr) is not int or rc_pbone_ptr <= 0
                or rc_pbone_ptr != pbone_ptr or int(pbone.as_pointer()) != rc_pbone_ptr
                or rc_session_id != active_tx.session_id or rc_tx_id != active_tx.tx_id
                or rc_seal is not getattr(active_tx, "_constraint_receipt_seal", None)
                or not isinstance(rc_before_ptrs, frozenset)
                or expected_ptr in rc_before_ptrs):
            raise RuntimeError("CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: registration and receipt mismatch")
        return

    # Only the exact instance returned by this invocation's constraints.new()
    # may be removed before it becomes registered. No name-based fallback.
    try:
        live = [candidate for candidate in pbone.constraints
                if int(candidate.as_pointer()) == expected_ptr]
        if len(live) != 1 or live[0] != con:
            raise RuntimeError("fresh Constraint no longer uniquely live on owning PoseBone")
        pbone.constraints.remove(live[0])
    except BaseException as exc:
        raise RuntimeError(
            f"CONSTRAINT_CREATION_CLEANUP_REMOVE_FAILED: ptr={expected_ptr}; "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    try:
        if any(int(candidate.as_pointer()) == expected_ptr for candidate in pbone.constraints):
            raise RuntimeError("original Constraint still live after C-API removal")
    except BaseException as exc:
        raise RuntimeError(
            f"CONSTRAINT_CREATION_CLEANUP_REMOVE_UNVERIFIED: ptr={expected_ptr}; "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if hasattr(active_tx, "_constraint_creation_receipts") and isinstance(active_tx._constraint_creation_receipts, dict):
        active_tx._constraint_creation_receipts.pop(expected_ptr, None)


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
    global _ACTIVE_TRANSACTION_STACK
    if active_tx is None and _ACTIVE_TRANSACTION_STACK:
        active_tx = _ACTIVE_TRANSACTION_STACK[-1]

    if active_tx is None:
        raise RuntimeError("Active transaction required for authorized constraint removal")

    if phase not in ("ROLLBACK", "POST_COMMIT_CLEANUP"):
        raise RuntimeError(f"Unauthorized constraint removal phase: '{phase}'")

    # Resolve the transaction record
    target_record: Optional[Dict[str, Any]] = None
    if phase == "ROLLBACK":
        # [INTRODUCED 2026-11-16T17:18:48+08:00]
        # FUNCTION: _authorized_remove_constraint
        # PURPOSE: Verify ROLLING_BACK state, active stack ownership, registry uniqueness, and creation receipt provenance
        # REASON: Task 10-B fix-4, require independent provenance receipts for constraint rollback removal
        if active_tx.state != _ArmRigTransactionState.ROLLING_BACK:
            raise RuntimeError(
                f"Unauthorized constraint removal in ROLLBACK phase: transaction state is {active_tx.state}, expected ROLLING_BACK"
            )
        if not _ACTIVE_TRANSACTION_STACK or active_tx not in _ACTIVE_TRANSACTION_STACK:
            raise RuntimeError(
                "Unauthorized constraint removal: transaction does not belong to active transaction stack"
            )

        allowed_records = list(getattr(active_tx, "created_constraints", []))
        matching_records = []
        if isinstance(con_record_or_ref, dict):
            rec_ptr = con_record_or_ref.get("con_ptr")
            matching_records = [rec for rec in allowed_records if rec.get("con_ptr") == rec_ptr]
        else:
            try:
                cand_ptr = con_record_or_ref.as_pointer()
            except ReferenceError:
                cand_ptr = None
            matching_records = [
                rec for rec in allowed_records
                if rec.get("con_ref") == con_record_or_ref or (cand_ptr is not None and rec.get("con_ptr") == cand_ptr)
            ]

        if len(matching_records) != 1:
            raise RuntimeError(
                f"Unauthorized constraint removal: expected exactly 1 registration record in ROLLBACK, got {len(matching_records)}"
            )
        target_record = matching_records[0]

        rec_ptr = target_record.get("con_ptr")
        rec_con_ref = target_record.get("con_ref")
        rec_pbone = target_record.get("pbone")

        receipts = getattr(active_tx, "_constraint_creation_receipts", {})
        if not isinstance(receipts, dict) or rec_ptr not in receipts:
            raise RuntimeError(
                f"Unauthorized constraint removal: no creation receipt found for constraint ptr={rec_ptr}"
            )

        receipt = receipts[rec_ptr]
        if not isinstance(receipt, tuple) or len(receipt) != 8:
            raise RuntimeError("Unauthorized constraint removal: creation receipt length must be exactly 8")

        rc_con, rc_con_ptr, rc_pbone, rc_pbone_ptr, rc_session_id, rc_tx_id, rc_seal, rc_before_ptrs = receipt

        if rc_seal is not getattr(active_tx, "_constraint_receipt_seal", None):
            raise RuntimeError("Unauthorized constraint removal: creation receipt seal mismatch")
        if rc_tx_id != active_tx.tx_id:
            raise RuntimeError(f"Unauthorized constraint removal: tx_id mismatch: {rc_tx_id} != {active_tx.tx_id}")
        if rc_session_id != active_tx.session_id:
            raise RuntimeError(f"Unauthorized constraint removal: session_id mismatch: {rc_session_id} != {active_tx.session_id}")
        if rc_con_ptr != rec_ptr or rc_con != rec_con_ref:
            raise RuntimeError("Unauthorized constraint removal: constraint reference or pointer mismatch with receipt")
        if rc_pbone != rec_pbone:
            raise RuntimeError("Unauthorized constraint removal: pose bone reference mismatch with receipt")
        if pbone is not None and rc_pbone != pbone:
            raise RuntimeError("Unauthorized constraint removal: target pose bone mismatch with receipt")

        if type(rc_pbone_ptr) is not int or rc_pbone_ptr <= 0:
            raise RuntimeError("Unauthorized constraint removal: invalid pose bone pointer in receipt")
        target_pbone = pbone if pbone is not None else rec_pbone
        try:
            target_pbone_ptr = int(target_pbone.as_pointer())
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Unauthorized constraint removal: pose bone pointer unreadable: {exc}") from exc
        if target_pbone_ptr != rc_pbone_ptr:
            raise RuntimeError(
                f"Unauthorized constraint removal: pose bone pointer mismatch: live={target_pbone_ptr} != receipt={rc_pbone_ptr}"
            )

        if not isinstance(rc_before_ptrs, frozenset):
            raise RuntimeError("Unauthorized constraint removal: creation receipt before_ptrs must be frozenset")

        snapshot = getattr(active_tx, "snapshot", None)
        if snapshot is None or not isinstance(snapshot, dict):
            raise RuntimeError("Unauthorized constraint removal: active transaction missing trusted snapshot")
        if active_tx.snapshot is not snapshot:
            raise RuntimeError("Unauthorized constraint removal: transaction snapshot identity mismatch")

        for b_name_snap, b_data_snap in snapshot.get("pose_bones", {}).items():
            if isinstance(b_data_snap, dict):
                for sc in b_data_snap.get("constraints", []):
                    if isinstance(sc, dict):
                        if sc.get("con_ptr") == rec_ptr or sc.get("con_ref") == rec_con_ref:
                            raise RuntimeError(
                                f"Unauthorized constraint removal: constraint ptr={rec_ptr} is an original snapshot constraint; deletion rejected"
                            )

        if rec_ptr in rc_before_ptrs:
            raise RuntimeError(
                f"Unauthorized constraint removal: constraint ptr={rec_ptr} was in pre-creation baseline; deletion rejected"
            )
    else:  # POST_COMMIT_CLEANUP
        allowed_records = list(getattr(active_tx, "stashed_constraints", [])) + list(getattr(active_tx, "uncleaned_stashed_constraints", []))
        if isinstance(con_record_or_ref, dict):
            rec_ptr = con_record_or_ref.get("con_ptr")
            for rec in allowed_records:
                if rec.get("con_ptr") == rec_ptr:
                    target_record = rec
                    break
        else:  # Constraint object
            try:
                cand_ptr = con_record_or_ref.as_pointer()
            except ReferenceError:
                cand_ptr = None
            for rec in allowed_records:
                if rec.get("con_ref") == con_record_or_ref or (cand_ptr is not None and rec.get("con_ptr") == cand_ptr):
                    target_record = rec
                    break

        if target_record is None:
            raise RuntimeError(
                f"Unauthorized constraint removal: resource not found in active transaction records for phase {phase}"
            )

    # Verify bone identity
    rec_pbone = target_record.get("pbone")
    rec_bone_name = target_record.get("bone_name")
    if pbone is None and rec_pbone is not None:
        pbone = rec_pbone
    if pbone is None:
        raise RuntimeError("Owning PoseBone is required for constraint removal")

    if rec_pbone is not None and rec_pbone != pbone:
        raise RuntimeError("Constraint record owning PoseBone reference mismatch")
    if rec_bone_name is not None and pbone.name != rec_bone_name:
        raise RuntimeError(f"Constraint record bone name mismatch: {pbone.name} != {rec_bone_name}")

    expected_ptr = target_record.get("con_ptr")
    con_ref = target_record.get("con_ref", target_record.get("con"))

    # Check if constraint is already deleted (idempotent removal)
    if con_ref is not None:
        try:
            live_ptr = con_ref.as_pointer()
            if expected_ptr is not None and live_ptr != expected_ptr:
                raise RuntimeError("Live constraint pointer changed unexpectedly")
        except ReferenceError:
            orig_name = target_record.get("orig_name")
            if any((orig_name and c.name == orig_name) or (expected_ptr and c.as_pointer() == expected_ptr) for c in pbone.constraints):
                raise RuntimeError("Stashed constraint original reference invalid")
            return True

    # Search for matching candidate in pbone.constraints
    matched_candidate = None
    for cand in list(pbone.constraints):
        try:
            if expected_ptr is not None and cand.as_pointer() == expected_ptr:
                if con_ref is not None and cand != con_ref:
                    raise RuntimeError("Constraint pointer matches but live reference differs")
                matched_candidate = cand
                break
            elif con_ref is not None and cand == con_ref:
                matched_candidate = cand
                break
        except ReferenceError:
            continue

    if matched_candidate is None:
        # Resource is already absent. Verify no substitute is touched.
        return True

    # Trigger fault injection before physical removal
    _trigger_fault_injection(
        "during_constraint_removal",
        {"pbone": pbone, "con": matched_candidate, "record": target_record, "phase": phase, "tx": active_tx},
    )

    # Physical removal via Blender C-API
    pbone.constraints.remove(matched_candidate)

    # Verify removal: re-enumerate constraints on pbone
    still_present = any(
        (expected_ptr is not None and c.as_pointer() == expected_ptr) or (con_ref is not None and c == con_ref)
        for c in pbone.constraints
    )
    if still_present:
        raise RuntimeError(f"Constraint removal verification failed: constraint still present on '{pbone.name}'")

    return True


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
    op_id = op_record.get("operation_id", "<unknown>")
    state = op_record.get("operation_state")

    if state in (_RelationshipOperationState.NO_EFFECT, _RelationshipOperationState.REVERTED):
        return

    if state == _RelationshipOperationState.PREPARED:
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.NO_EFFECT,
        )
        return

    if state == _RelationshipOperationState.RECOVERY_UNCERTAIN:
        restoration_errors.append(
            f"Relationship rollback '{op_id}' remains RECOVERY_UNCERTAIN; refusing undo"
        )
        return

    try:
        _trigger_fault_injection(
            "during_relationship_rollback_undo",
            {"op": op_record, "tx": active_tx},
        )
    except BaseException as exc:
        if op_record.get("operation_state") in (
            _RelationshipOperationState.APPLYING,
            _RelationshipOperationState.APPLIED_VERIFIED,
            _RelationshipOperationState.CONFIRMED,
        ):
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
        # [INTRODUCED 2026-11-11T22:38:48+08:00]
        # FUNCTION: _authorized_revert_relationship_record
        # PURPOSE: Propagate RECOVERY_UNCERTAIN evidence or classify FAILED-C from verified relationship state
        # REASON: Task 10-B fix-2, TEST-127 / TEST-149
        if op_record.get("operation_state") == _RelationshipOperationState.RECOVERY_UNCERTAIN:
            restoration_errors.append(
                f"Relationship rollback '{op_id}' fault (RECOVERY_UNCERTAIN): {type(exc).__name__}: {exc}"
            )
        else:
            restoration_errors.append(
                f"Relationship rollback '{op_id}' fault: {type(exc).__name__}: {exc}"
            )
        return

    src_id = op_record.get("source_identity", {})
    tgt_id = op_record.get("target_identity", {})
    orig_rel = op_record.get("original_relationship_state", {})
    category = orig_rel.get("category", "OWNERSHIP_UNKNOWN")
    mutation = op_record.get("intended_mutation")

    if mutation in ("CONSTRAINT_TARGET_ASSIGN", "CONSTRAINT_POLE_TARGET_ASSIGN"):
        field = op_record.get("field", "target" if mutation == "CONSTRAINT_TARGET_ASSIGN" else "pole_target")
        subtarget_field = op_record.get("subtarget_field", "subtarget" if mutation == "CONSTRAINT_TARGET_ASSIGN" else "pole_subtarget")

        pbone = op_record.get("pbone_ref", orig_rel.get("pbone_ref"))
        pbone_ptr = op_record.get("pbone_ptr", orig_rel.get("pbone_ptr"))
        con = op_record.get("con_ref", orig_rel.get("con_ref"))
        con_ptr = op_record.get("con_ptr", orig_rel.get("con_ptr"))

        orig_target = op_record.get("orig_target_ref", orig_rel.get("orig_target_ref"))
        orig_target_ptr = op_record.get("orig_target_ptr", orig_rel.get("orig_target_ptr"))
        orig_subtarget = op_record.get("orig_subtarget", orig_rel.get("orig_subtarget", ""))

        dest_target = op_record.get("dest_target_ref", orig_rel.get("dest_target_ref"))
        dest_target_ptr = op_record.get("dest_target_ptr", orig_rel.get("dest_target_ptr"))

        # Verify pbone and con identity
        con_alive = False
        if con is not None and con_ptr is not None:
            try:
                if con.as_pointer() == con_ptr:
                    con_alive = True
            except ReferenceError:
                con_alive = False

        if not con_alive:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Constraint identity lost during target relationship rollback for {mutation}")
            return

        # Verify orig_target identity if not None
        if orig_target is not None:
            try:
                live_target_ptr = orig_target.as_pointer()
                if orig_target_ptr is not None and live_target_ptr != orig_target_ptr:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original constraint target pointer changed during rollback")
                    return
                if _find_live_object_by_identity(orig_target, orig_target_ptr) is None:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original constraint target object destroyed during rollback")
                    return
            except ReferenceError:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append("Original constraint target destroyed during rollback")
                return

        if state == _RelationshipOperationState.APPLYING:
            # An interrupted two-field assignment can change only the target,
            # only the subtarget, or both. Never infer NO_EFFECT from the
            # target alone; preserve reversible partial writes.
            try:
                if "dest_subtarget" not in op_record and "dest_subtarget" not in orig_rel:
                    raise RuntimeError("Destination subtarget evidence missing")
                dest_subtarget = op_record.get("dest_subtarget", orig_rel.get("dest_subtarget"))
                curr_target = getattr(con, field, None)
                curr_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
                classification = _classify_constraint_target_pair_effect(
                    curr_target, curr_sub,
                    orig_target, orig_target_ptr, orig_subtarget,
                    dest_target, dest_target_ptr, dest_subtarget,
                )
            except Exception as exc:
                active_tx.update_relationship_mutation_state(
                    op_record, _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(
                    f"Constraint target rollback '{op_id}' pair inspection failed: {type(exc).__name__}: {exc}"
                )
                return
            active_tx.update_relationship_mutation_state(op_record, classification)
            if classification == _RelationshipOperationState.NO_EFFECT:
                return
            if classification == _RelationshipOperationState.RECOVERY_UNCERTAIN:
                restoration_errors.append(
                    f"Constraint target rollback '{op_id}' observed unrecognized target/subtarget pair"
                )
                return
            state = _RelationshipOperationState.APPLIED_VERIFIED

        if state not in (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.CONFIRMED):
            restoration_errors.append(
                f"Relationship operation '{op_id}' in unexpected state '{state}' during target rollback"
            )
            return

        try:
            setattr(con, field, orig_target)
            if hasattr(con, subtarget_field):
                setattr(con, subtarget_field, orig_subtarget)

            rev_target = getattr(con, field, None)
            rev_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
            rev_target_ptr = rev_target.as_pointer() if (rev_target and hasattr(rev_target, "as_pointer")) else None

            tgt_matches = (rev_target == orig_target if orig_target is not None else rev_target is None)
            ptr_matches = (rev_target_ptr == orig_target_ptr)
            sub_matches = (rev_sub == orig_subtarget)

            if not (tgt_matches and ptr_matches and sub_matches):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(f"Failed to verify constraint {field} reversion")
                return
        except BaseException as be:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Exception during constraint {field} reversion: {be}")
            return

        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.REVERTED,
        )
        return

    elif mutation == "OBJECT_PARENT_ASSIGN":
        obj = op_record.get("controller_ref", orig_rel.get("controller_ref"))
        obj_ptr = op_record.get("controller_ptr", orig_rel.get("controller_ptr"))
        orig_parent = op_record.get("orig_parent_ref", orig_rel.get("orig_parent_ref"))
        orig_parent_ptr = op_record.get("orig_parent_ptr", orig_rel.get("orig_parent_ptr"))
        orig_parent_name = op_record.get("orig_parent_name", orig_rel.get("orig_parent_name"))
        orig_inv = op_record.get("orig_matrix_parent_inverse", orig_rel.get("orig_matrix_parent_inverse"))
        if orig_inv is None:
            orig_inv = Matrix.Identity(4)

        live_obj = _find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if live_obj is None:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Controller identity lost during object parent rollback for '{op_id}'")
            return

        if state == _RelationshipOperationState.APPLYING:
            curr_p = getattr(live_obj, "parent", None)
            curr_p_ptr = curr_p.as_pointer() if (curr_p is not None and hasattr(curr_p, "as_pointer")) else None
            curr_inv = getattr(live_obj, "matrix_parent_inverse", Matrix.Identity(4)).copy()

            p_changed = False
            if orig_parent is None and curr_p is not None:
                p_changed = True
            elif orig_parent is not None and (curr_p is None or curr_p != orig_parent or curr_p_ptr != orig_parent_ptr):
                p_changed = True

            inv_changed = not _matrix_equals(orig_inv, curr_inv, tol=1e-5)
            if not p_changed and not inv_changed:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.NO_EFFECT,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.APPLIED_VERIFIED,
            )
            state = _RelationshipOperationState.APPLIED_VERIFIED

        if state not in (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.CONFIRMED):
            restoration_errors.append(
                f"Relationship operation '{op_id}' in unexpected state '{state}' during object parent rollback"
            )
            return

        live_parent = None
        if orig_parent is not None:
            try:
                if orig_parent_ptr is not None and orig_parent.as_pointer() != orig_parent_ptr:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original parent pointer changed during rollback")
                    return
                live_parent = _find_live_object_by_identity(orig_parent, orig_parent_ptr)
                if live_parent is None:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original parent object destroyed during rollback")
                    return
                if orig_parent_name and orig_parent_name in bpy.data.objects:
                    if bpy.data.objects[orig_parent_name] != live_parent:
                        active_tx.update_relationship_mutation_state(
                            op_record,
                            _RelationshipOperationState.RECOVERY_UNCERTAIN,
                        )
                        restoration_errors.append(f"Original parent name '{orig_parent_name}' occupied by another object")
                        return
            except ReferenceError:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append("Original parent destroyed during rollback")
                return

        try:
            live_obj.parent = live_parent
            live_obj.matrix_parent_inverse = orig_inv.copy()
        except BaseException as be:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Exception during object parent reversion: {be}")
            return

        rev_p = getattr(live_obj, "parent", None)
        rev_inv = getattr(live_obj, "matrix_parent_inverse", Matrix.Identity(4))
        p_ok = (rev_p == live_parent)
        inv_ok = _matrix_equals(rev_inv, orig_inv, tol=1e-5)
        if p_ok and inv_ok:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.REVERTED,
            )
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append("Object parent restoration RNA verification failed")
        return

    elif mutation in ("COLLECTION_CHILD_LINK", "COLLECTION_CHILD_UNLINK"):
        parent_col = op_record.get("parent_col_ref", orig_rel.get("parent_col_ref"))
        parent_ptr = op_record.get("parent_col_ptr", orig_rel.get("parent_col_ptr"))
        child_col = op_record.get("child_col_ref", orig_rel.get("child_col_ref"))
        child_ptr = op_record.get("child_col_ptr", orig_rel.get("child_col_ptr"))

        live_parent = _find_live_collection_by_identity(parent_col, parent_ptr)
        live_child = _find_live_collection_by_identity(child_col, child_ptr)

        if state == _RelationshipOperationState.APPLYING:
            if live_parent is None or live_child is None:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                return
            is_linked = _is_child_collection_linked_by_identity(live_parent, live_child, child_ptr)
            if mutation == "COLLECTION_CHILD_LINK":
                if not is_linked:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.NO_EFFECT,
                    )
                    return
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.APPLIED_VERIFIED,
                )
                state = _RelationshipOperationState.APPLIED_VERIFIED
            else:
                if is_linked:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.NO_EFFECT,
                    )
                    return
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.APPLIED_VERIFIED,
                )
                state = _RelationshipOperationState.APPLIED_VERIFIED

        if state not in (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.CONFIRMED):
            restoration_errors.append(
                f"Relationship operation '{op_id}' in unexpected state '{state}' during collection child rollback"
            )
            return

        if live_parent is None or live_child is None:
            if mutation == "COLLECTION_CHILD_LINK" and not _is_child_collection_linked_by_identity(parent_col, child_col, child_ptr):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.REVERTED,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append("Parent or child collection identity lost during collection child rollback")
            return

        if mutation == "COLLECTION_CHILD_LINK":
            if _is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                try:
                    live_parent.children.unlink(live_child)
                except Exception as e:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append(f"Failed to unlink child collection '{live_child.name}': {e}")
                    return
            if not _is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.REVERTED,
                )
            else:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(f"Child collection '{live_child.name}' still linked after unlink")
            return
        else:
            if not _is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                try:
                    live_parent.children.link(live_child)
                except Exception as e:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        _RelationshipOperationState.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append(f"Failed to relink child collection '{live_child.name}': {e}")
                    return
            if _is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.REVERTED,
                )
            else:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(f"Child collection '{live_child.name}' not linked after restoration")
            return

    col_ref = src_id.get("ref", op_record.get("source_reference"))
    col_ptr = src_id.get("ptr")
    obj_ref = tgt_id.get("ref", op_record.get("target_reference"))
    obj_ptr = tgt_id.get("ptr")

    live_col = _find_live_collection_by_identity(col_ref, col_ptr)
    live_obj = _find_live_object_by_identity(obj_ref, obj_ptr) if obj_ptr is not None else None

    if state == _RelationshipOperationState.APPLYING:
        if live_col is None or live_obj is None or category == "OWNERSHIP_UNKNOWN":
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object APPLYING rollback '{op_id}' identity/ownership unproven")
            return

        is_linked = _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        if mutation == "COLLECTION_OBJECT_LINK":
            if not is_linked:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.NO_EFFECT,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.APPLIED_VERIFIED,
            )
            state = _RelationshipOperationState.APPLIED_VERIFIED
        elif mutation == "COLLECTION_OBJECT_UNLINK":
            if is_linked:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    _RelationshipOperationState.NO_EFFECT,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.APPLIED_VERIFIED,
            )
            state = _RelationshipOperationState.APPLIED_VERIFIED
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            return

    if state not in (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.CONFIRMED):
        restoration_errors.append(
            f"Relationship operation '{op_id}' in unexpected state '{state}' during rollback"
        )
        return

    if live_col is None or live_obj is None or category == "OWNERSHIP_UNKNOWN":
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        restoration_errors.append(f"Collection/Object rollback '{op_id}' identity or ownership unproven")
        return

    if mutation == "COLLECTION_OBJECT_LINK":
        if category != "TX_ADDED":
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object link rollback '{op_id}' lacks TX_ADDED authority")
            return
        try:
            if _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                live_col.objects.unlink(live_obj)
            still_linked = _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        except BaseException as exc:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object unlink rollback '{op_id}' failed: {type(exc).__name__}: {exc}")
            return

        if still_linked:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object link rollback '{op_id}' failed RNA unlink verification")
            return

        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.REVERTED,
        )
    elif mutation == "COLLECTION_OBJECT_UNLINK":
        if category != "TX_UNLINKED_ORIGINAL":
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object unlink rollback '{op_id}' lacks TX_UNLINKED_ORIGINAL authority")
            return
        try:
            if not _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                live_col.objects.link(live_obj)
            now_linked = _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        except BaseException as exc:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object relink rollback '{op_id}' failed: {type(exc).__name__}: {exc}")
            return

        if not now_linked:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object unlink rollback '{op_id}' failed RNA relink verification")
            return

        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.REVERTED,
        )
    else:
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        restoration_errors.append(f"Unknown relationship rollback mutation '{mutation}' for '{op_id}'")


def _authorized_restore_snapshot_collection_child(
    parent_ref: bpy.types.Collection,
    parent_ptr: int,
    child_ref: bpy.types.Collection,
    child_ptr: int,
    restoration_errors: List[str],
) -> None:
    """Restore a baseline Collection hierarchy edge by original live identity."""
    parent = _find_live_collection_by_identity(parent_ref, parent_ptr)
    child = _find_live_collection_by_identity(child_ref, child_ptr)
    if parent is None or child is None:
        restoration_errors.append(
            f"Snapshot Collection hierarchy identity unproven: parent={parent_ptr}, child={child_ptr}"
        )
        return
    if _is_child_collection_linked_by_identity(parent, child, child_ptr):
        return
    try:
        parent.children.link(child)
    except BaseException as exc:
        restoration_errors.append(
            f"Snapshot Collection hierarchy relink failed: {type(exc).__name__}: {exc}"
        )
        return
    if not _is_child_collection_linked_by_identity(parent, child, child_ptr):
        restoration_errors.append(
            f"Snapshot Collection hierarchy relink not reflected in RNA: parent={parent_ptr}, child={child_ptr}"
        )


def _authorized_ensure_snapshot_collection_link(
    col: Optional[bpy.types.Collection],
    obj_ref: bpy.types.Object,
    obj_ptr: Optional[int],
    restoration_errors: List[str],
) -> None:
    """Layer 3 restoration of a pre-existing snapshot Collection <-> Object membership by verified identity."""
    if col is None:
        return
    try:
        col_ptr = col.as_pointer()
    except ReferenceError:
        restoration_errors.append("Snapshot collection reference destroyed before membership restoration")
        return

    live_col = _find_live_collection_by_identity(col, col_ptr)
    if live_col is None:
        restoration_errors.append("Snapshot collection identity lost during membership restoration")
        return

    if obj_ptr is None:
        try:
            obj_ptr = obj_ref.as_pointer()
        except ReferenceError:
            restoration_errors.append("Snapshot member object destroyed before membership restoration")
            return

    live_obj = _find_live_object_by_identity(obj_ref, obj_ptr)
    if live_obj is None:
        restoration_errors.append("Snapshot member object identity lost during membership restoration")
        return

    if not _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
        try:
            live_col.objects.link(live_obj)
        except BaseException as exc:
            restoration_errors.append(
                f"Snapshot Collection/Object membership restore failed (col={col_ptr}, obj={obj_ptr}): "
                f"{type(exc).__name__}: {exc}"
            )
            return
        if not _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
            restoration_errors.append(
                f"Snapshot Collection/Object membership restore did not take effect "
                f"(col={col_ptr}, obj={obj_ptr})"
            )


def _authorized_restore_collection_object_relationships(
    active_tx: Optional[Any],
    snapshot: Dict[str, Any],
    restoration_errors: List[str],
    phase: str = "ALL",
) -> None:
    """Layer 3 authoritative rollback and restoration of Collection <-> Object relationships."""
    if phase in ("ALL", "PRE_CONTROLLER_REMOVE") and active_tx is not None:
        logged_records = list(getattr(active_tx, "prepared_relationship_mutations", []))
        logged_link_pairs = set()
        for op_record in reversed(logged_records):
            if op_record.get("intended_mutation") == "COLLECTION_OBJECT_LINK":
                src_id = op_record.get("source_identity", {})
                tgt_id = op_record.get("target_identity", {})
                logged_link_pairs.add((src_id.get("ptr"), tgt_id.get("ptr")))
                _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

        # A legacy created_collection_links entry does NOT authorize destructive
        # unlink. Only an actual Layer 3 relationship operation may be undone.
        for link_rec in reversed(list(getattr(active_tx, "created_collection_links", []))):
            col_ref = link_rec.get("col_ref")
            col_ptr = link_rec.get("col_ptr")
            obj_ref = link_rec.get("obj_ref")
            obj_ptr = link_rec.get("obj_ptr")
            if (col_ptr, obj_ptr) in logged_link_pairs:
                continue
            live_col = _find_live_collection_by_identity(col_ref, col_ptr)
            live_obj = _find_live_object_by_identity(obj_ref, obj_ptr) if obj_ptr is not None else None
            if (live_col is not None and live_obj is not None
                    and _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)):
                restoration_errors.append(
                    f"Collection/Object rollback unauthorized without Layer 3 log: "
                    f"collection_ptr={col_ptr}, object_ptr={obj_ptr}; no unlink performed"
                )

    if phase in ("ALL", "POST_CONTROLLER_RESTORE"):
        if active_tx is not None:
            for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
                if op_record.get("intended_mutation") == "COLLECTION_OBJECT_UNLINK":
                    _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

        # Ensure pre-existing controller collection memberships from snapshot are intact by identity
        controllers_snap = snapshot.get("controllers", {})
        for c_name, c_snap in controllers_snap.items():
            if not c_snap.get("exists"):
                continue
            original_ref = c_snap.get("obj_ref")
            original_ptr = c_snap.get("obj_ptr")
            if original_ref is None or original_ptr is None:
                continue
            live_original = _find_live_object_by_identity(original_ref, original_ptr)
            if live_original is None:
                continue
            if active_tx is not None and _verify_controller_object_transaction_authority(
                live_original, active_tx,
            ) != 'SNAPSHOT_ORIGINAL':
                # Never restore memberships of merely observed external objects.
                continue
            col_refs = c_snap.get("collection_refs")
            col_ptrs = c_snap.get("collection_ptrs")
            if col_refs is not None and col_ptrs is not None and len(col_refs) == len(col_ptrs):
                for c_ref, c_ptr in zip(col_refs, col_ptrs):
                    live_col = _find_live_collection_by_identity(c_ref, c_ptr)
                    if live_col is not None:
                        _authorized_ensure_snapshot_collection_link(
                            live_col, live_original, original_ptr, restoration_errors
                        )
            else:
                if c_snap.get("collections"):
                    restoration_errors.append(
                        f"Controller '{c_name}' snapshot Collection identity metadata missing; "
                        "refusing membership restoration by name"
                    )

        # Ensure stashed objects' original collection memberships are intact by identity
        if active_tx is not None:
            for stashed in getattr(active_tx, "stashed_objects", []):
                obj = stashed.get("stashed_obj")
                obj_ptr = stashed.get("stashed_obj_ptr")
                live_stashed = _find_live_object_by_identity(obj, obj_ptr) if (obj and obj_ptr) else obj
                if live_stashed is None:
                    continue
                s_col_refs = stashed.get("collection_refs")
                s_col_ptrs = stashed.get("collection_ptrs")
                if s_col_refs is not None and s_col_ptrs is not None and len(s_col_refs) == len(s_col_ptrs):
                    for c_ref, c_ptr in zip(s_col_refs, s_col_ptrs):
                        live_col = _find_live_collection_by_identity(c_ref, c_ptr)
                        if live_col is not None:
                            _authorized_ensure_snapshot_collection_link(
                                live_col, live_stashed, obj_ptr, restoration_errors
                            )
                else:
                    if stashed.get("collections"):
                        restoration_errors.append(
                            "Stashed object snapshot Collection identity metadata missing; "
                            "refusing membership restoration by name"
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
    live_obj = _find_live_object_by_identity(obj_ref, obj_ptr)
    if live_obj is None or orig_inverse is None:
        restoration_errors.append("Snapshot object parent authority missing: original object/inverse unavailable")
        return
    if parent_ref is None:
        if parent_ptr is not None:
            restoration_errors.append("Snapshot object parent reference missing for recorded pointer")
            return
        live_parent = None
    else:
        if not isinstance(parent_ptr, int) or parent_ptr <= 0:
            restoration_errors.append("Snapshot object parent original pointer missing")
            return
        live_parent = _find_live_object_by_identity(parent_ref, parent_ptr)
        if live_parent is None:
            restoration_errors.append("Snapshot object parent identity lost; refusing reparent")
            return
    try:
        current_parent = live_obj.parent
        current_ptr = current_parent.as_pointer() if current_parent is not None else None
        current_inv = live_obj.matrix_parent_inverse
        if (current_parent == live_parent and current_ptr == parent_ptr
                and _matrix_equals(current_inv, orig_inverse)):
            return
        live_obj.parent = live_parent
        live_obj.matrix_parent_inverse = orig_inverse.copy()
        final_parent = live_obj.parent
        final_ptr = final_parent.as_pointer() if final_parent is not None else None
        if (final_parent != live_parent or final_ptr != parent_ptr
                or not _matrix_equals(live_obj.matrix_parent_inverse, orig_inverse)):
            restoration_errors.append("Snapshot object parent restoration failed identity/inverse verification")
    except BaseException as exc:
        restoration_errors.append(
            f"Snapshot object parent restoration failed: {type(exc).__name__}: {exc}"
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
    label = f"{bone_name}/{sc.get('name', '<unknown>')}"
    planned = []
    previous = []

    def target_matches(current: Any, expected: Any, expected_ptr: Optional[int]) -> bool:
        if expected is None:
            return current is None and expected_ptr is None
        if current is None or type(expected_ptr) is not int or expected_ptr <= 0:
            return False
        try:
            return (current == expected
                    and int(current.as_pointer()) == expected_ptr
                    and _find_live_object_by_identity(expected, expected_ptr) is not None)
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            return False

    try:
        original_con = sc.get("con_ref")
        original_con_ptr = sc.get("con_ptr")
        if (original_con is None or type(original_con_ptr) is not int
                or original_con_ptr <= 0 or con != original_con
                or int(con.as_pointer()) != original_con_ptr
                or int(original_con.as_pointer()) != original_con_ptr):
            raise RuntimeError("original Constraint identity mismatch")

        for field, subfield in (("target", "subtarget"), ("pole_target", "pole_subtarget")):
            has_target = hasattr(con, field)
            has_sub = hasattr(con, subfield)
            expected_target = sc.get(field)
            expected_sub = sc.get(subfield, "")
            ptr_key = f"{field}_ptr"
            if ptr_key not in sc:
                raise RuntimeError(f"snapshot lacks captured original pointer for {field}")
            expected_ptr = sc[ptr_key]
            if not isinstance(expected_sub, str):
                raise RuntimeError(f"{subfield} snapshot is not a string")
            if not has_target:
                if (has_sub or expected_target is not None or expected_ptr is not None
                        or expected_sub != ""):
                    raise RuntimeError(f"{field} unavailable but snapshot contains relationship")
                continue
            if not has_sub and expected_sub:
                raise RuntimeError(f"{subfield} property absent but snapshot is nonempty")
            if not target_matches(expected_target, expected_target, expected_ptr):
                raise RuntimeError(f"{field} original Object identity unproven/dead")
            current_target = getattr(con, field)
            current_ptr = None
            if current_target is not None:
                current_ptr = int(current_target.as_pointer())
                if (current_ptr <= 0
                        or _find_live_object_by_identity(current_target, current_ptr) is None):
                    raise RuntimeError(f"{field} current Object identity unreadable/dead")
            current_sub = getattr(con, subfield) if has_sub else ""
            if not isinstance(current_sub, str):
                raise RuntimeError(f"{subfield} current value is not a string")
            planned.append((field, subfield, has_sub, expected_target, expected_ptr, expected_sub))
            previous.append((field, subfield, has_sub, current_target, current_ptr, current_sub))
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        restoration_errors.append(f"BUG-07 snapshot Constraint target authority denied [{label}]: {exc}")
        return

    if not planned:
        return

    try:
        for field, subfield, has_sub, expected_target, expected_ptr, expected_sub in planned:
            if not target_matches(getattr(con, field), expected_target, expected_ptr):
                setattr(con, field, expected_target)
            if has_sub and getattr(con, subfield) != expected_sub:
                setattr(con, subfield, expected_sub)

        for field, subfield, has_sub, expected_target, expected_ptr, expected_sub in planned:
            if not target_matches(getattr(con, field), expected_target, expected_ptr):
                raise RuntimeError(f"{field} RNA did not restore original pointer")
            if has_sub and getattr(con, subfield) != expected_sub:
                raise RuntimeError(f"{subfield} RNA did not restore original string")
    except BaseException as exc:
        # A pair of RNA setters is not physically atomic. Compensate any
        # partial writes back to the exact pre-call values, without hiding error.
        compensation_errors = []
        for field, subfield, has_sub, old_target, old_ptr, old_sub in reversed(previous):
            try:
                actual_target = getattr(con, field)
                if not target_matches(actual_target, old_target, old_ptr):
                    setattr(con, field, old_target)
                if has_sub and getattr(con, subfield) != old_sub:
                    setattr(con, subfield, old_sub)
                if not target_matches(getattr(con, field), old_target, old_ptr):
                    raise RuntimeError(f"{field} compensation RNA identity mismatch")
                if has_sub and getattr(con, subfield) != old_sub:
                    raise RuntimeError(f"{subfield} compensation RNA value mismatch")
            except BaseException as compensation_exc:
                compensation_errors.append(
                    f"{field}/{subfield}: {type(compensation_exc).__name__}: {compensation_exc}"
                )
        restoration_errors.append(
            f"BUG-07 snapshot Constraint targets restore failed [{label}]: "
            f"{type(exc).__name__}: {exc}; compensation="
            + ("OK" if not compensation_errors else "FAILED [" + "; ".join(compensation_errors) + "]")
        )


def _verify_failed_isolation_controller_recovery_authority(
    arm: bpy.types.Object,
    obj: bpy.types.Object,
    snapshot: Dict[str, Any],
    tx: Any,
    expected_role: Optional[tuple[str, str]],
) -> tuple[bool, str]:
    """Verify that a FAILED-isolated transaction holds legal authority to restore original Controller state.

    Must verify all 8 conditions from Task 10-B dynamic acceptance requirements:
    1. Armature identity and liveness
    2. Session identity and isolation registration
    3. Transaction identity and context binding
    4. Snapshot reference and trustworthiness consistency
    5. Controller original reference, pointer, and non-creation baseline
    6. Original IK constraint binding provenance
    7. Absence of borrowing by any foreign Armature
    8. FAILED isolation class (FAILED-B or FAILED-C only; FAILED-D strictly denied)
    """
    if not isinstance(tx, _ArmRigTransactionContext):
        return False, "Transaction is not an _ArmRigTransactionContext instance"

    if tx.state != _ArmRigTransactionState.FAILED:
        return False, f"Transaction state is {tx.state!r}, expected FAILED"

    # 1. Armature identity
    if arm is None or not isinstance(arm, bpy.types.Object) or arm.type != "ARMATURE":
        return False, "Armature object is missing or invalid type"
    try:
        arm_ptr = int(arm.as_pointer())
        if arm_ptr <= 0 or tx.arm is not arm or tx.arm_ptr != arm_ptr:
            return False, "Armature reference/pointer does not match transaction"
    except (AttributeError, ReferenceError, TypeError, ValueError) as exc:
        return False, f"Armature pointer access error: {exc}"

    # 2. Session identity
    session_id = getattr(tx, "session_id", None)
    if not isinstance(session_id, str) or not session_id:
        return False, "Transaction session_id is missing or empty"

    session_rec = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
    if session_rec is None:
        return False, f"Session ID {session_id!r} not found in _MANAGED_ARMATURE_IDENTITIES"
    if tx.session_record is not session_rec or session_rec.registry_session_id != session_id:
        return False, "Session record mismatch with transaction"
    if session_rec.original_blender_ref is not arm or session_rec.registration_pointer != arm_ptr:
        return False, "Session record registration does not match Armature"

    # [INTRODUCED 2026-11-11T19:47:00+08:00]
    # FUNCTION: _verify_failed_isolation_controller_recovery_authority
    # PURPOSE: Enforce strict bidirectional consistency between isolation record, tx context, failure class, and session state
    # REASON: Task 10-B fix-1: complete isolation record consistency validation for TEST-131, 136, 147, 155
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(session_id)
    if not isinstance(iso_rec, dict):
        return False, f"No active isolation record in _ISOLATED_FAILED_ARMATURES for session {session_id!r}"
    if iso_rec.get("registry_session_id") != session_id:
        return False, f"Isolation record registry_session_id {iso_rec.get('registry_session_id')!r} != session_id {session_id!r}"
    if iso_rec.get("transaction_id") != tx.tx_id:
        return False, f"Isolation record transaction_id {iso_rec.get('transaction_id')!r} != tx.tx_id {tx.tx_id!r}"
    tx_ctx = iso_rec.get("transaction_context")
    if tx_ctx is None or tx_ctx is not tx:
        return False, "Isolation record transaction_context is missing, None, or does not match active tx"

    failure_class = iso_rec.get("failure_class")
    if failure_class in (_FailedTransactionClass.FAILED_D.value, "FAILED-D"):
        return False, "FAILED-D tombstones are strictly denied controller recovery authority"
    if failure_class not in (
        _FailedTransactionClass.FAILED_B.value,
        _FailedTransactionClass.FAILED_C.value,
        "FAILED-B",
        "FAILED-C",
    ):
        return False, f"Unsupported failure class for recovery: {failure_class!r}"

    tx_failure_class = getattr(tx, "failure_class", None)
    if failure_class != tx_failure_class:
        return False, f"Isolation record failure_class {failure_class!r} != tx.failure_class {tx_failure_class!r}"

    iso_state = session_rec.isolation_state
    if iso_state in (
        _ArmatureIsolationState.TOMBSTONED_FAILED_D,
        _ArmatureIsolationState.ARCHIVED_RETIRED,
        _ArmatureIsolationState.NONE,
    ):
        return False, f"Armature session isolation state {iso_state!r} is not an active FAILED isolation"

    if failure_class in (_FailedTransactionClass.FAILED_B.value, "FAILED-B"):
        if iso_state != _ArmatureIsolationState.ISOLATED_FAILED_B:
            return False, f"Failure class FAILED-B requires isolation_state ISOLATED_FAILED_B, got {iso_state!r}"
    elif failure_class in (_FailedTransactionClass.FAILED_C.value, "FAILED-C"):
        if iso_state != _ArmatureIsolationState.ISOLATED_FAILED_C:
            return False, f"Failure class FAILED-C requires isolation_state ISOLATED_FAILED_C, got {iso_state!r}"

    rec_iso_state_val = iso_state.value if hasattr(iso_state, "value") else str(iso_state)
    if iso_rec.get("isolation_state") != rec_iso_state_val:
        return False, f"Isolation record isolation_state {iso_rec.get('isolation_state')!r} != session_rec.isolation_state {rec_iso_state_val!r}"

    if session_rec.liveness_status == _ArmatureLivenessStatus.INVALIDATED_DEAD:
        return False, "Armature is marked INVALIDATED_DEAD"

    id_ver = _verify_armature_session_identity_record(session_rec, candidate_arm=arm)
    if not id_ver.get("is_valid", False):
        return False, f"Armature session identity record is invalid: {'; '.join(id_ver.get('reasons', []))}"

    # 4. Snapshot reference and trustworthiness consistency
    if not isinstance(snapshot, dict):
        return False, "Snapshot is not a valid dictionary"

    trusted_snap = iso_rec.get("snapshot_reference")
    if not iso_rec.get("snapshot_trusted", False) or trusted_snap is None:
        return False, "Isolation record indicates snapshot is not trusted or missing"
    if iso_rec.get("evidence_status") == "RECOVERY_EVIDENCE_INSUFFICIENT":
        return False, "Isolation record evidence_status is RECOVERY_EVIDENCE_INSUFFICIENT"
    if trusted_snap is not snapshot or tx.snapshot is not snapshot:
        return False, "Snapshot reference does not match trusted isolation snapshot or tx.snapshot"

    # 5. Controller original reference, pointer, and baseline
    if obj is None or not isinstance(obj, bpy.types.Object) or obj.type != "EMPTY":
        return False, "Controller object is missing or not an EMPTY"
    try:
        obj_ptr = int(obj.as_pointer())
        if obj_ptr <= 0 or _find_live_object_by_identity(obj, obj_ptr) is None:
            return False, "Controller object is not live or cannot be identified"
    except (AttributeError, ReferenceError, TypeError, ValueError) as exc:
        return False, f"Controller pointer access error: {exc}"

    if not isinstance(tx.entry_object_ptrs, (frozenset, set)):
        return False, "Transaction entry_object_ptrs baseline is missing"
    if obj_ptr not in tx.entry_object_ptrs:
        return False, f"Controller ptr={obj_ptr} was not present in transaction entry_object_ptrs baseline"

    created_regs = [
        r for r in getattr(tx, "created_controller_objects", [])
        if isinstance(r, dict) and r.get("obj_ptr") == obj_ptr
    ]
    if created_regs:
        return False, f"Controller ptr={obj_ptr} is recorded as transaction-created; not an original controller"

    saved = None
    saved_name = None
    for orig_name, orig_rec in snapshot.get("controllers", {}).items():
        if isinstance(orig_rec, dict) and orig_rec.get("obj_ptr") == obj_ptr and orig_rec.get("obj_ref") == obj:
            if saved is not None:
                return False, f"Multiple snapshot controllers match ptr={obj_ptr}"
            saved = orig_rec
            saved_name = orig_name

    if saved is None:
        return False, f"Controller ptr={obj_ptr} has no matching entry in trusted snapshot"
    if not saved.get("exists", False) or saved.get("type") != "EMPTY":
        return False, f"Snapshot controller record for ptr={obj_ptr} is not a valid pre-existing EMPTY"

    role = _controller_role_for_name(saved_name)
    if role is None:
        return False, f"Cannot determine controller role for snapshot name {saved_name!r}"
    if expected_role is not None and role != expected_role:
        return False, f"Controller role {role!r} does not match expected role {expected_role!r}"

    # 6. Original IK constraint binding provenance
    if not _controller_constraint_binding_proven(arm, obj, role, snapshot):
        return False, f"Controller binding to IK constraint on role {role!r} cannot be proven from snapshot"

    # 7. Absence of borrowing by any foreign Armature
    if _controller_is_borrowed_by_other_armature(arm, obj, role):
        return False, f"Controller is borrowed by another Armature constraint"

    return True, "AUTHORIZED"


def _rollback_arm_rig_state(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Restore the Arm IK rig state precisely to the recorded snapshot."""
    _trigger_fault_injection(
        "during_rollback_execution",
        {"arm": arm, "snapshot": snapshot, "tx": active_tx},
    )
    restoration_errors: List[str] = []

    # Step 0: Authoritatively revert constraint target/pole target relationships FIRST,
    # before any transaction-created target controller objects are deleted.
    if active_tx is not None:
        for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
            if op_record.get("intended_mutation") in (
                "CONSTRAINT_TARGET_ASSIGN",
                "CONSTRAINT_POLE_TARGET_ASSIGN",
            ):
                _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

    # Step 0.5: Authoritatively revert Object Parent relationships before created controller objects are deleted
    if active_tx is not None:
        for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
            if op_record.get("intended_mutation") == "OBJECT_PARENT_ASSIGN":
                _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

    # Step 1: Controller cleanup, stashed object restoration, and transform restoration
    # 1.0a: Revert transaction-created Collection <-> Object links via Layer 3 before removing created controllers
    _authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase="PRE_CONTROLLER_REMOVE",
    )

    # 1.0b: Remove only controllers proven created AFTER this transaction's
    # entry baseline. A forged or stale registry entry is never deletion authority.
    if active_tx is not None:
        if active_tx.arm is not arm or active_tx.snapshot is not snapshot:
            restoration_errors.append("Controller cleanup rejected: transaction/snapshot ownership mismatch")
        else:
            # Validate the entire creation ledger before ANY destructive write.
            # A missing or forged list record must not silently hide a live
            # transaction-created Object from rollback verification.
            registry = getattr(active_tx, 'created_controller_objects', None)
            receipts = getattr(active_tx, '_controller_creation_receipts', None)
            entry_ptrs = active_tx.entry_object_ptrs
            proof_errors: List[str] = []
            validated: Dict[int, Dict[str, Any]] = {}
            if not isinstance(registry, list) or not isinstance(receipts, dict):
                proof_errors.append('Created controller registry/receipt ledger is malformed')
            elif not isinstance(entry_ptrs, (set, frozenset)):
                proof_errors.append('Created controller entry-pointer baseline is unavailable')
            else:
                for record in registry:
                    if not isinstance(record, dict):
                        proof_errors.append('Created controller registry contains a non-dictionary record')
                        continue
                    obj_ref, obj_ptr = record.get('obj_ref'), record.get('obj_ptr')
                    if obj_ref is None or type(obj_ptr) is not int or obj_ptr <= 0:
                        proof_errors.append('Created controller registry entry has invalid identity fields')
                        continue
                    if obj_ptr in validated:
                        proof_errors.append(f'Duplicate created controller identity pointer {obj_ptr}')
                        continue
                    validated[obj_ptr] = record
                    if obj_ptr in entry_ptrs:
                        proof_errors.append(f'Created controller pointer {obj_ptr} existed at transaction entry')
                    if _controller_role_for_name(record.get('created_name')) is None:
                        proof_errors.append(f'Created controller pointer {obj_ptr} lacks an original controller role')
                    receipt = receipts.get(obj_ptr)
                    if (not isinstance(receipt, tuple) or len(receipt) != 4
                            or receipt[0] is not obj_ref
                            or receipt[1] != active_tx.session_id
                            or receipt[2] != active_tx.tx_id
                            or receipt[3] is not active_tx._controller_receipt_seal):
                        proof_errors.append(f'Created controller pointer {obj_ptr} has no matching original receipt')
                if set(validated) != set(receipts):
                    proof_errors.append('Created controller registry and creation receipts diverged')
            if proof_errors:
                # Fail closed rather than partially deleting objects under an
                # inconsistent or incomplete transaction ownership ledger.
                restoration_errors.extend(proof_errors)
            else:
                for obj_ptr, record in validated.items():
                    obj_ref = record['obj_ref']
                    live_obj = _find_live_object_by_identity(obj_ref, obj_ptr)
                    if live_obj is None:
                        # Do not substitute a new Blender Object sharing the name.
                        continue
                    if _verify_controller_object_transaction_authority(
                        live_obj, active_tx, created_only=True,
                    ) != 'TX_CREATED':
                        restoration_errors.append(
                            f'Controller deletion refused: pointer {obj_ptr} lacks transaction creation authority'
                        )
                        continue
                    # A foreign Armature referring to a newly-created controller
                    # removes exclusive deletion rights. Keep that resource and
                    # surface an explicit rollback failure for Coordinator isolation.
                    role = _controller_role_for_name(record['created_name'])
                    if _controller_is_borrowed_by_other_armature(active_tx.arm, live_obj, role):
                        restoration_errors.append(
                            f'Controller deletion refused: pointer {obj_ptr} is referenced by another Armature'
                        )
                        continue
                    bpy.data.objects.remove(live_obj, do_unlink=True)
                    if _find_live_object_by_identity(obj_ref, obj_ptr) is not None:
                        restoration_errors.append(
                            f'Transaction-created controller removal failed (pointer {obj_ptr})'
                        )

    controllers_snap = snapshot.get("controllers", {})
    for c_name, c_snap in controllers_snap.items():
        if not c_snap["exists"]:
            # If snapshot recorded controller did not exist, transaction-owned
            # controllers have already been cleaned up by identity above.
            # External same-name objects MUST NOT be deleted.
            continue

        original_ref = c_snap["obj_ref"]
        original_ptr = c_snap["obj_ptr"]
        original_name = c_snap["obj_name"]

        live_original = _find_live_object_by_identity(
            original_ref,
            original_ptr,
        )

        if live_original is None:
            restoration_errors.append(
                f"Original controller identity lost: {original_name}"
            )
            continue
        controller_authorized = False
        if active_tx is None:
            controller_authorized = True
        elif active_tx.state in (_ArmRigTransactionState.ACTIVE, _ArmRigTransactionState.ROLLING_BACK):
            if _verify_controller_object_transaction_authority(
                live_original, active_tx,
            ) == 'SNAPSHOT_ORIGINAL':
                controller_authorized = True
            else:
                # An unrelated same-name controller may have been observed by the
                # snapshot; observing is not authority to restore or reparent it.
                continue
        elif active_tx.state == _ArmRigTransactionState.FAILED:
            auth_ok, auth_reason = _verify_failed_isolation_controller_recovery_authority(
                arm=arm,
                obj=live_original,
                snapshot=snapshot,
                tx=active_tx,
                expected_role=_controller_role_for_name(original_name),
            )
            if auth_ok:
                controller_authorized = True
            else:
                restoration_errors.append(
                    f"FAILED isolation controller recovery authority denied for '{original_name}': {auth_reason}"
                )
                continue
        else:
            restoration_errors.append(
                f"Controller recovery rejected: unsupported transaction state {active_tx.state!r} for '{original_name}'"
            )
            continue

        if not controller_authorized:
            continue

        name_owner = bpy.data.objects.get(original_name)

        if (
            name_owner is not None
            and name_owner != live_original
        ):
            restoration_errors.append(
                "Original controller name occupied by "
                f"another object: {original_name}"
            )
            continue

        if live_original.name != original_name:
            live_original.name = original_name

        # Check if parent was already restored via Layer 3 relationship record
        parent_restored_via_tx = False
        if active_tx is not None:
            for op_rec in getattr(active_tx, "prepared_relationship_mutations", []):
                if op_rec.get("intended_mutation") == "OBJECT_PARENT_ASSIGN":
                    if op_rec.get("controller_ptr") == original_ptr or op_rec.get("controller_ref") == live_original:
                        parent_restored_via_tx = True
                        break

        if not parent_restored_via_tx:
            _authorized_restore_snapshot_object_parent(
                live_original, original_ptr, c_snap.get("parent"),
                c_snap.get("parent_ptr"), c_snap.get("matrix_parent_inverse"),
                restoration_errors,
            )
        else:
            # A logged rollback owns the undo: never overwrite it with a second
            # unlogged parent write. Check that it actually restored the snapshot.
            snap_parent = c_snap.get("parent")
            snap_parent_ptr = c_snap.get("parent_ptr")
            curr_parent = live_original.parent
            curr_ptr = curr_parent.as_pointer() if curr_parent is not None else None
            if (curr_parent != snap_parent or curr_ptr != snap_parent_ptr
                    or not _matrix_equals(live_original.matrix_parent_inverse,
                                          c_snap.get("matrix_parent_inverse"))):
                restoration_errors.append(
                    f"Controller '{original_name}' logged parent rollback does not match snapshot"
                )

        live_original.rotation_mode = c_snap["rotation_mode"]
        live_original.location = c_snap["location"].copy()
        live_original.rotation_euler = c_snap["rotation_euler"].copy()
        live_original.rotation_quaternion = c_snap["rotation_quaternion"].copy()
        live_original.rotation_axis_angle = tuple(c_snap["rotation_axis_angle"])
        live_original.scale = c_snap["scale"].copy()
        if live_original.type == "EMPTY":
            if c_snap.get("empty_display_type") is not None:
                live_original.empty_display_type = c_snap["empty_display_type"]
            if c_snap.get("empty_display_size") is not None:
                live_original.empty_display_size = c_snap["empty_display_size"]

    # Also ensure any other stashed objects from active_tx have their names restored before re-linking
    if active_tx is not None:
        for stashed in getattr(active_tx, "stashed_objects", []):
            obj = stashed.get("stashed_obj")
            obj_ptr = stashed.get("stashed_obj_ptr")
            orig_name = stashed.get("original_name")
            live_stashed = _find_live_object_by_identity(obj, obj_ptr) if (obj and obj_ptr) else obj
            if live_stashed is not None:
                if orig_name and live_stashed.name != orig_name:
                    name_owner = bpy.data.objects.get(orig_name)
                    if name_owner is None or name_owner == live_stashed:
                        live_stashed.name = orig_name

    # 1.1: Restore unlinked original Collection <-> Object memberships via Layer 3
    _authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase="POST_CONTROLLER_RESTORE",
    )

    # Step 2: Pose bones and constraints restoration
    pose_bones_snap = snapshot.get("pose_bones", {}) if isinstance(snapshot, dict) else {}

    # [INTRODUCED 2026-11-16T19:15:00+08:00]
    # FUNCTION: _rollback_arm_rig_state
    # PURPOSE: Comprehensive pre-deletion ledger, receipt, PoseBone identity, and live constraint membership validation before any removal
    # REASON: Task 10-B fix-4 Round 1/2, close pre-check gaps on bone_name/PoseBone identity and live constraint membership to prevent partial deletion
    constraint_creation_audit_passed = True
    if active_tx is not None:
        proof_errors: List[str] = []

        # Snapshot identity and transaction ownership verification
        if (active_tx.arm is not arm or active_tx.snapshot is not snapshot
                or not isinstance(snapshot, dict) or not isinstance(pose_bones_snap, dict)):
            proof_errors.append("Constraint rollback rejected: transaction/snapshot ownership mismatch")
            constraint_creation_audit_passed = False

        created_constraints = getattr(active_tx, "created_constraints", None)
        receipts = getattr(active_tx, "_constraint_creation_receipts", None)

        # 1. 登记表结构合法
        if not isinstance(created_constraints, list):
            proof_errors.append("Constraint rollback rejected: created_constraints registry is not a list")
            constraint_creation_audit_passed = False

        # 2. 凭据表结构合法
        if not isinstance(receipts, dict):
            proof_errors.append("Constraint rollback rejected: _constraint_creation_receipts is not a dict")
            constraint_creation_audit_passed = False

        if constraint_creation_audit_passed:
            if created_constraints or receipts:
                if active_tx.state != _ArmRigTransactionState.ROLLING_BACK:
                    proof_errors.append(
                        f"Constraint rollback rejected: transaction state is {active_tx.state}, expected ROLLING_BACK"
                    )
                if not _ACTIVE_TRANSACTION_STACK or active_tx not in _ACTIVE_TRANSACTION_STACK:
                    proof_errors.append(
                        "Constraint rollback rejected: transaction does not belong to active transaction stack"
                    )

            # 3. 无重复资源身份 & 登记表记录合法
            reg_ptrs: List[int] = []
            reg_refs: List[Any] = []
            for rec in created_constraints:
                if not isinstance(rec, dict):
                    proof_errors.append("Constraint rollback rejected: registry record is not a dict")
                    continue
                c_ptr = rec.get("con_ptr")
                c_ref = rec.get("con_ref")
                pbone_ref = rec.get("pbone")
                b_name_rec = rec.get("bone_name")
                if (c_ref is None or type(c_ptr) is not int or c_ptr <= 0
                        or pbone_ref is None or not isinstance(b_name_rec, str) or not b_name_rec):
                    proof_errors.append(f"Constraint rollback rejected: invalid registry entry fields (ptr={c_ptr})")
                    continue
                if c_ptr in reg_ptrs or any(r == c_ref for r in reg_refs):
                    proof_errors.append(f"Constraint rollback rejected: duplicate constraint identity (ptr={c_ptr}) in registry")
                else:
                    reg_ptrs.append(c_ptr)
                    reg_refs.append(c_ref)

            rc_ptrs: List[int] = []
            for k in receipts.keys():
                if type(k) is not int or k <= 0:
                    proof_errors.append(f"Constraint rollback rejected: invalid receipt key {k}")
                    continue
                if k in rc_ptrs:
                    proof_errors.append(f"Constraint rollback rejected: duplicate receipt pointer {k}")
                else:
                    rc_ptrs.append(k)

            # 4. 登记表和凭据表指针集合完全一致
            set_reg_ptrs = set(reg_ptrs)
            set_rc_ptrs = set(rc_ptrs)
            if set_reg_ptrs != set_rc_ptrs:
                proof_errors.append(
                    f"Constraint rollback rejected: pointer mismatch between registry and receipts: "
                    f"registry_only={set_reg_ptrs - set_rc_ptrs}, receipts_only={set_rc_ptrs - set_reg_ptrs}"
                )

            # Collect all snapshot original constraint pointers and refs
            all_snapshot_con_ptrs = set()
            all_snapshot_con_refs = set()
            for b_name_s, b_data_s in pose_bones_snap.items():
                if isinstance(b_data_s, dict):
                    for sc in b_data_s.get("constraints", []):
                        if isinstance(sc, dict):
                            if sc.get("con_ptr") is not None:
                                all_snapshot_con_ptrs.add(sc["con_ptr"])
                            if sc.get("con_ref") is not None:
                                all_snapshot_con_refs.add(sc["con_ref"])

            # 5. 逐一验证每份凭据、PoseBone 实时身份与当前约束集合归属
            seal = getattr(active_tx, "_constraint_receipt_seal", None)
            for rec in created_constraints:
                if not isinstance(rec, dict):
                    continue
                c_ptr = rec.get("con_ptr")
                c_ref = rec.get("con_ref")
                rec_pbone = rec.get("pbone")
                rec_bone_name = rec.get("bone_name")

                # 核验登记 bone_name 与所属 PoseBone 实时身份一致
                live_pbone = None
                if not isinstance(rec_bone_name, str) or not rec_bone_name:
                    proof_errors.append(f"Constraint rollback rejected: invalid bone_name for ptr={c_ptr}")
                elif rec_bone_name not in pose_bones_snap:
                    proof_errors.append(
                        f"Constraint rollback rejected: registered bone_name '{rec_bone_name}' not in snapshot for ptr={c_ptr}"
                    )
                elif arm is None or getattr(arm, "pose", None) is None or getattr(arm.pose, "bones", None) is None:
                    proof_errors.append(f"Constraint rollback rejected: armature pose bones unavailable for ptr={c_ptr}")
                else:
                    live_pbone = arm.pose.bones.get(rec_bone_name)
                    if live_pbone is None:
                        proof_errors.append(
                            f"Constraint rollback rejected: PoseBone '{rec_bone_name}' not found on armature for ptr={c_ptr}"
                        )
                    elif rec_pbone is None or live_pbone != rec_pbone:
                        proof_errors.append(
                            f"Constraint rollback rejected: PoseBone reference mismatch for bone '{rec_bone_name}' (ptr={c_ptr})"
                        )
                    else:
                        try:
                            if getattr(rec_pbone, "name", None) != rec_bone_name:
                                proof_errors.append(
                                    f"Constraint rollback rejected: PoseBone live name '{getattr(rec_pbone, 'name', None)}' != registered bone_name '{rec_bone_name}' (ptr={c_ptr})"
                                )
                        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                            proof_errors.append(f"Constraint rollback rejected: PoseBone reference dead when reading name for ptr={c_ptr}")

                if c_ptr not in receipts:
                    proof_errors.append(f"Constraint rollback rejected: missing receipt for registered constraint ptr={c_ptr}")
                    continue

                rc = receipts[c_ptr]
                # 每份凭据均为长度恰好为 8 的元组
                if not isinstance(rc, tuple) or len(rc) != 8:
                    proof_errors.append(f"Constraint rollback rejected: receipt for ptr={c_ptr} is not an 8-tuple")
                    continue

                rc_con, rc_con_ptr, rc_pbone, rc_pbone_ptr, rc_session_id, rc_tx_id, rc_seal, rc_before_ptrs = rc

                # Constraint 引用、指针一致
                if rc_con is None or rc_con != c_ref or rc_con_ptr != c_ptr:
                    proof_errors.append(f"Constraint rollback rejected: receipt constraint mismatch for ptr={c_ptr}")
                else:
                    try:
                        if int(rc_con.as_pointer()) != c_ptr:
                            proof_errors.append(f"Constraint rollback rejected: live constraint pointer mismatch for ptr={c_ptr}")
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                        proof_errors.append(f"Constraint rollback rejected: constraint reference dead for ptr={c_ptr}")

                # PoseBone 引用、指针一致
                if rc_pbone is None or rc_pbone != rec_pbone or (live_pbone is not None and rc_pbone != live_pbone):
                    proof_errors.append(f"Constraint rollback rejected: receipt pose bone reference mismatch for ptr={c_ptr}")
                elif type(rc_pbone_ptr) is not int or rc_pbone_ptr <= 0:
                    proof_errors.append(f"Constraint rollback rejected: receipt pose bone pointer invalid for ptr={c_ptr}")
                else:
                    try:
                        live_pb_ptr = int(rc_pbone.as_pointer())
                        if live_pb_ptr != rc_pbone_ptr:
                            proof_errors.append(f"Constraint rollback rejected: live pose bone pointer mismatch for ptr={c_ptr}")
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                        proof_errors.append(f"Constraint rollback rejected: pose bone dead for ptr={c_ptr}")

                # 核验 Constraint 引用和指针确实存在于登记的 PoseBone 当前约束集合
                if rec_pbone is not None and c_ref is not None and type(c_ptr) is int and c_ptr > 0:
                    try:
                        bone_cons = list(rec_pbone.constraints)
                        matched_cands = []
                        cand_mismatch = False
                        for cand in bone_cons:
                            cand_ptr = int(cand.as_pointer())
                            if cand_ptr == c_ptr or cand == c_ref:
                                if cand_ptr != c_ptr or cand != c_ref:
                                    cand_mismatch = True
                                matched_cands.append(cand)
                        if cand_mismatch or len(matched_cands) != 1:
                            proof_errors.append(
                                f"Constraint rollback rejected: constraint ptr={c_ptr} not uniquely present on PoseBone '{rec_bone_name}'"
                            )
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                        proof_errors.append(
                            f"Constraint rollback rejected: failed to enumerate constraints on PoseBone '{rec_bone_name}' for ptr={c_ptr}"
                        )

                # Session ID 一致
                if rc_session_id != active_tx.session_id:
                    proof_errors.append(f"Constraint rollback rejected: session_id mismatch for ptr={c_ptr}")

                # Transaction ID 一致
                if rc_tx_id != active_tx.tx_id:
                    proof_errors.append(f"Constraint rollback rejected: tx_id mismatch for ptr={c_ptr}")

                # Seal 一致
                if rc_seal is not seal or seal is None:
                    proof_errors.append(f"Constraint rollback rejected: seal mismatch for ptr={c_ptr}")

                # 创建前基线为 frozenset
                if not isinstance(rc_before_ptrs, frozenset):
                    proof_errors.append(f"Constraint rollback rejected: before_ptrs not frozenset for ptr={c_ptr}")
                elif c_ptr in rc_before_ptrs:
                    # Constraint 不属于创建前基线
                    proof_errors.append(f"Constraint rollback rejected: constraint ptr={c_ptr} in before_ptrs")

                # Constraint 不属于事务 Snapshot 原始资源
                if c_ptr in all_snapshot_con_ptrs or c_ref in all_snapshot_con_refs:
                    proof_errors.append(f"Constraint rollback rejected: constraint ptr={c_ptr} is snapshot original")

        if proof_errors:
            constraint_creation_audit_passed = False
            restoration_errors.extend(proof_errors)

    for b_name, b_snap in pose_bones_snap.items():
        pbone = arm.pose.bones.get(b_name)
        if pbone is None:
            continue

        pbone.rotation_mode = b_snap["rotation_mode"]
        pbone.location = b_snap["location"].copy()
        pbone.rotation_euler = b_snap["rotation_euler"].copy()
        pbone.rotation_quaternion = b_snap["rotation_quaternion"].copy()
        pbone.rotation_axis_angle = tuple(b_snap["rotation_axis_angle"])
        pbone.scale = b_snap["scale"].copy()
        pbone.matrix_basis = b_snap["matrix_basis"].copy()

        pbone.lock_ik_x = b_snap["lock_ik_x"]
        pbone.lock_ik_y = b_snap["lock_ik_y"]
        pbone.lock_ik_z = b_snap["lock_ik_z"]
        pbone.use_ik_limit_x = b_snap["use_ik_limit_x"]
        pbone.use_ik_limit_y = b_snap["use_ik_limit_y"]
        pbone.use_ik_limit_z = b_snap["use_ik_limit_z"]
        pbone.ik_min_x = b_snap["ik_min_x"]
        pbone.ik_max_x = b_snap["ik_max_x"]
        pbone.ik_min_y = b_snap["ik_min_y"]
        pbone.ik_max_y = b_snap["ik_max_y"]
        pbone.ik_min_z = b_snap["ik_min_z"]
        pbone.ik_max_z = b_snap["ik_max_z"]

        # Constraints non-destructive restoration
        saved_cons = b_snap.get("constraints", [])
        saved_con_refs = {sc["con_ref"] for sc in saved_cons if "con_ref" in sc}

        # 2.1: Remove ONLY constraints explicitly registered as created by this transaction via Layer 3
        if active_tx is not None and constraint_creation_audit_passed:
            for reg_con in list(getattr(active_tx, "created_constraints", [])):
                if reg_con.get("bone_name") == b_name or reg_con.get("pbone") == pbone:
                    try:
                        _authorized_remove_constraint(
                            pbone,
                            reg_con,
                            phase="ROLLBACK",
                            active_tx=active_tx,
                        )
                    except Exception as ce:
                        restoration_errors.append(
                            f"Failed to remove transaction-created constraint '{reg_con.get('created_name')}': {ce}"
                        )

        # 2.2: Restore names and mutes for any stashed constraints on this bone
        if active_tx is not None:
            for item in getattr(active_tx, "stashed_constraints", []):
                if item["pbone"] == pbone:
                    c = item["con"]
                    if c in pbone.constraints.values():
                        c.name = item["orig_name"]
                        c.mute = item["orig_mute"]

        # 2.3: Reconcile and restore all saved constraints
        for sc in saved_cons:
            # Task 10-B-6
            # Resolve original constraint without substitution

            original_con = sc.get("con_ref")
            original_ptr = sc.get("con_ptr")

            if original_con is None or original_ptr is None:
                restoration_errors.append(
                    f"Missing snapshot identity: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            try:
                live_ptr = original_con.as_pointer()
            except ReferenceError:
                restoration_errors.append(
                    f"Original constraint destroyed: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            if live_ptr != original_ptr:
                restoration_errors.append(
                    f"Original constraint pointer changed: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            con = None

            for candidate in pbone.constraints:
                if candidate.as_pointer() == original_ptr:
                    con = candidate
                    break

            if con is None:
                restoration_errors.append(
                    f"Original constraint absent from live chain: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            if con.type != sc["type"]:
                restoration_errors.append(
                    f"Original constraint type mismatch: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            con.name = sc["name"]

            con.influence = sc["influence"]
            con.mute = sc["mute"]

            for prop, val in sc.get("generic_props", {}).items():
                if prop in ("target", "pole_target", "subtarget", "pole_subtarget"):
                    continue
                try:
                    _trigger_fault_injection("during_constraint_property_restore", {
                        "bone": b_name, "con": sc["name"], "prop": prop, "val": val
                    })
                    if hasattr(con, prop):
                        if isinstance(val, (Vector, Euler, Quaternion, Matrix)):
                            setattr(con, prop, val.copy())
                        elif isinstance(val, tuple):
                            curr_val = getattr(con, prop)
                            if hasattr(curr_val, "__len__"):
                                for arr_i, el in enumerate(val):
                                    curr_val[arr_i] = el
                            else:
                                setattr(con, prop, val)
                        else:
                            setattr(con, prop, val)
                except Exception as ce:
                    restoration_errors.append(
                        f"Failed to restore property '{prop}' on constraint '{sc['name']}' "
                        f"on bone '{b_name}' with value {val!r}: {ce}"
                    )

            if active_tx is None:
                _authorized_restore_snapshot_constraint_targets_without_tx(
                    con, sc, b_name, restoration_errors,
                )
            else:
                # When active_tx is present, verify targets match snapshot after Step 0 reversion
                if hasattr(con, "target") and con.target != sc.get("target"):
                    restoration_errors.append(
                        f"Constraint '{con.name}' target does not match snapshot after rollback: "
                        f"{con.target} != {sc.get('target')}"
                    )
                if hasattr(con, "subtarget") and con.subtarget != sc.get("subtarget", ""):
                    restoration_errors.append(
                        f"Constraint '{con.name}' subtarget does not match snapshot after rollback: "
                        f"'{con.subtarget}' != '{sc.get('subtarget', '')}'"
                    )
                if hasattr(con, "pole_target") and con.pole_target != sc.get("pole_target"):
                    restoration_errors.append(
                        f"Constraint '{con.name}' pole_target does not match snapshot after rollback: "
                        f"{con.pole_target} != {sc.get('pole_target')}"
                    )
                if hasattr(con, "pole_subtarget") and con.pole_subtarget != sc.get("pole_subtarget", ""):
                    restoration_errors.append(
                        f"Constraint '{con.name}' pole_subtarget does not match snapshot after rollback: "
                        f"'{con.pole_subtarget}' != '{sc.get('pole_subtarget', '')}'"
                    )

            if sc["type"] == "IK":
                con.chain_count = sc.get("chain_count", 0)
                con.use_tail = sc.get("use_tail", True)
                con.use_stretch = sc.get("use_stretch", False)
                con.pole_angle = sc.get("pole_angle", 0.0)
                con.iterations = sc.get("iterations", 500)
            elif sc["type"] == "COPY_ROTATION":
                con.target_space = sc.get("target_space", "WORLD")
                con.owner_space = sc.get("owner_space", "WORLD")
                con.mix_mode = sc.get("mix_mode", "REPLACE")
                con.use_x = sc.get("use_x", True)
                con.use_y = sc.get("use_y", True)
                con.use_z = sc.get("use_z", True)
                con.invert_x = sc.get("invert_x", False)
                con.invert_y = sc.get("invert_y", False)
                con.invert_z = sc.get("invert_z", False)
                con.use_offset = sc.get("use_offset", False)

        # 2.4: Restore relative ordering of original constraints by identity
        saved_ptrs = [sc["con_ptr"] for sc in saved_cons if sc.get("con_ptr")]
        live_ptr_to_idx = {c.as_pointer(): idx for idx, c in enumerate(pbone.constraints)}
        for i in range(len(saved_ptrs)):
            for j in range(i + 1, len(saved_ptrs)):
                ptr_i = saved_ptrs[i]
                ptr_j = saved_ptrs[j]
                if ptr_i in live_ptr_to_idx and ptr_j in live_ptr_to_idx:
                    idx_i = live_ptr_to_idx[ptr_i]
                    idx_j = live_ptr_to_idx[ptr_j]
                    if idx_i > idx_j:
                        pbone.constraints.move(idx_i, idx_j)
                        live_ptr_to_idx = {c.as_pointer(): idx for idx, c in enumerate(pbone.constraints)}

    # Step 3: Collection hierarchy rollback. Both relationship undo and
    # collection deletion must prove the same creation ownership.
    # Validate the ENTIRE receipt ledger before the first Collection mutation:
    # rejecting one forged entry must not leave earlier entries partly deleted.
    verified_created_collections = {}
    collection_rollback_authorized = active_tx is not None
    if active_tx is not None:
        try:
            registered = getattr(active_tx, "created_collections", None)
            receipts = getattr(active_tx, "_collection_creation_receipts", None)
            entry_ptrs = getattr(active_tx, "entry_collection_ptrs", None)
            session = getattr(active_tx, "session_record", None)
            if not isinstance(registered, list) or not isinstance(receipts, dict):
                raise RuntimeError("Collection registry/receipt ledger unavailable")
            if not isinstance(entry_ptrs, (set, frozenset)):
                raise RuntimeError("Collection entry baseline unavailable")
            if (session is None
                    or getattr(active_tx, "session_id", None) is None
                    or _MANAGED_ARMATURE_IDENTITIES.get(active_tx.session_id) is not session
                    or session.original_blender_ref is not active_tx.arm):
                raise RuntimeError("Collection transaction session identity mismatch")
            for rec in registered:
                if not isinstance(rec, dict):
                    raise RuntimeError("Non-dictionary created Collection record")
                col_ptr = rec.get("col_ptr")
                col_ref = rec.get("col_ref")
                parent_ref = rec.get("initial_parent")
                parent_ptr = rec.get("initial_parent_ptr")
                if (not isinstance(col_ptr, int) or col_ptr <= 0
                        or not isinstance(parent_ptr, int) or parent_ptr <= 0
                        or col_ptr in entry_ptrs
                        or col_ptr in verified_created_collections
                        or col_ref is None or parent_ref is None):
                    raise RuntimeError(f"Invalid/duplicate Collection identity: {col_ptr!r}")
                receipt = receipts.get(col_ptr)
                if (not isinstance(receipt, tuple) or len(receipt) != 5
                        or receipt[0] != col_ref
                        or receipt[1] != parent_ref
                        or receipt[2] != active_tx.session_id
                        or receipt[3] != active_tx.tx_id
                        or receipt[4] is not active_tx._collection_receipt_seal):
                    raise RuntimeError(f"Collection creation receipt mismatch: {col_ptr}")
                try:
                    live_col_ptr = int(col_ref.as_pointer())
                    live_parent_ptr = int(parent_ref.as_pointer())
                except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                    raise RuntimeError(f"Collection/parent identity unreadable: {col_ptr}") from exc
                if (live_col_ptr != col_ptr or live_parent_ptr != parent_ptr
                        or _find_live_collection_by_identity(col_ref, col_ptr) is None
                        or _find_live_collection_by_identity(parent_ref, parent_ptr) is None):
                    raise RuntimeError(f"Collection/parent is not the originally registered live identity: {col_ptr}")
                verified_created_collections[col_ptr] = (col_ref, parent_ref, parent_ptr, receipt)
            if set(verified_created_collections) != set(receipts):
                raise RuntimeError("Collection registry and receipt ledger do not have identical identities")
        except Exception as exc:
            collection_rollback_authorized = False
            restoration_errors.append(
                f"COLLECTION_ROLLBACK_AUTHORITY_UNPROVEN: {exc}; refusing all Collection child undo/deletion"
            )

    # 3.0: Revert only the relationship edges authorized at creation.
    # NO_EFFECT, PREPARED and REVERTED contain no outstanding C-API undo.
    if active_tx is not None and collection_rollback_authorized:
        relationship_ops = getattr(active_tx, "prepared_relationship_mutations", [])
        for op_record in reversed(list(relationship_ops)):
            mutation = op_record.get("intended_mutation")
            if mutation not in ("COLLECTION_CHILD_LINK", "COLLECTION_CHILD_UNLINK"):
                continue
            state = op_record.get("operation_state")
            if state in (
                _RelationshipOperationState.NO_EFFECT,
                _RelationshipOperationState.REVERTED,
                _RelationshipOperationState.PREPARED,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            ):
                _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)
                continue
            orig_rel = op_record.get("original_relationship_state")
            parent_ptr = op_record.get("parent_col_ptr")
            child_ptr = op_record.get("child_col_ptr")
            parent_ref = op_record.get("parent_col_ref")
            child_ref = op_record.get("child_col_ref")
            owned = verified_created_collections.get(child_ptr)
            valid_edge = (
                isinstance(orig_rel, dict)
                and owned is not None
                and owned[0] == child_ref
                and owned[1] == parent_ref
                and owned[2] == parent_ptr
                and _find_live_collection_by_identity(parent_ref, parent_ptr) is not None
                and _find_live_collection_by_identity(child_ref, child_ptr) is not None
            )
            if mutation == "COLLECTION_CHILD_LINK":
                valid_edge = (
                    valid_edge and orig_rel.get("linked") is False
                    and orig_rel.get("category") == "TX_ADDED"
                )
            else:
                prior_link = any(
                    isinstance(previous, dict)
                    and previous.get("intended_mutation") == "COLLECTION_CHILD_LINK"
                    and previous.get("parent_col_ptr") == parent_ptr
                    and previous.get("child_col_ptr") == child_ptr
                    and previous.get("parent_col_ref") == parent_ref
                    and previous.get("child_col_ref") == child_ref
                    and isinstance(previous.get("original_relationship_state"), dict)
                    and previous["original_relationship_state"].get("linked") is False
                    and previous["original_relationship_state"].get("category") == "TX_ADDED"
                    and previous.get("operation_state") in (
                        _RelationshipOperationState.APPLIED_VERIFIED,
                        _RelationshipOperationState.CONFIRMED,
                        _RelationshipOperationState.REVERTED,
                    )
                    for previous in relationship_ops
                )
                valid_edge = (
                    valid_edge and orig_rel.get("linked") is True
                    and orig_rel.get("category") == "TX_UNLINKED_ORIGINAL"
                    and prior_link
                )
            if not valid_edge:
                restoration_errors.append(
                    f"COLLECTION_RELATION_ROLLBACK_AUTHORITY_UNPROVEN: "
                    f"{op_record.get('operation_id', '<unknown>')}; refusing relationship undo"
                )
                active_tx.update_relationship_mutation_state(
                    op_record, _RelationshipOperationState.RECOVERY_UNCERTAIN,
                )
                continue
            _authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

    # 3.1: Delete only receipt-verified collections with NO remaining owners,
    # members, children, parents or Blender users. Never unlink a parent as a
    # side effect of deletion: an unexpected parent edge is external ownership.
    if active_tx is not None and collection_rollback_authorized:
        for col_ptr, (col_ref, parent_ref, parent_ptr, original_receipt) in verified_created_collections.items():
            target_col = _find_live_collection_by_identity(col_ref, col_ptr)
            if target_col is None:
                restoration_errors.append(
                    f"Verified transaction Collection ptr={col_ptr} was destroyed before rollback deletion"
                )
                continue
            try:
                member_count = len(target_col.objects)
                child_count = len(target_col.children)
                parent_count = sum(
                    1 for p in bpy.data.collections
                    if p != target_col and _is_child_collection_linked_by_identity(p, target_col, col_ptr)
                ) + sum(
                    1 for scene in bpy.data.scenes
                    if (getattr(scene, "collection", None) is not None
                        and _is_child_collection_linked_by_identity(scene.collection, target_col, col_ptr))
                )
                user_count = int(target_col.users)
            except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                restoration_errors.append(
                    f"Cannot inspect verified Collection ptr={col_ptr} dependencies: {exc}"
                )
                continue
            if member_count or child_count or parent_count or user_count:
                restoration_errors.append(
                    f"Verified Collection ptr={col_ptr} still has dependencies "
                    f"(members={member_count}, children={child_count}, "
                    f"parents={parent_count}, users={user_count}); refusing deletion"
                )
                continue
            # Final revalidation immediately before destructive Blender call;
            # fault hooks in preceding relationship undo may have changed logs.
            final_records = [
                rec for rec in active_tx.created_collections
                if isinstance(rec, dict) and rec.get("col_ptr") == col_ptr
            ]
            latest_receipt = active_tx._collection_creation_receipts.get(col_ptr)
            if (_find_live_collection_by_identity(col_ref, col_ptr) != target_col
                    or _find_live_collection_by_identity(parent_ref, parent_ptr) is None
                    or col_ptr in active_tx.entry_collection_ptrs
                    or len(final_records) != 1
                    or final_records[0].get("col_ref") != col_ref
                    or final_records[0].get("initial_parent") != parent_ref
                    or final_records[0].get("initial_parent_ptr") != parent_ptr
                    or latest_receipt != original_receipt
                    or original_receipt[4] is not active_tx._collection_receipt_seal):
                restoration_errors.append(f"Collection ptr={col_ptr} identity/authority changed before deletion")
                continue
            try:
                bpy.data.collections.remove(target_col)
            except Exception as exc:
                restoration_errors.append(f"Failed to remove verified Collection ptr={col_ptr}: {exc}")
                continue
            if _find_live_collection_by_identity(col_ref, col_ptr) is not None:
                restoration_errors.append(f"Verified Collection ptr={col_ptr} still exists after removal")

    char_col_snap = snapshot.get("character_collection", {})
    if not char_col_snap.get("existed", False):
        # Transaction-owned collections are handled
        # exclusively by active_tx.created_collections.
        #
        # Never delete a collection merely because
        # its name is "Character".
        pass
    else:
        # ------------------------------------------------------
        # Task 10-B-7
        # Identity-safe restoration of Character collection
        # ------------------------------------------------------
        orig_name = char_col_snap.get("name")
        col = char_col_snap.get("col_ref")
        original_ptr = char_col_snap.get("col_ptr")

        if col is None or original_ptr is None:
            restoration_errors.append(
                "Character collection snapshot identity missing"
            )
        else:
            try:
                live_ptr = col.as_pointer()
            except ReferenceError:
                restoration_errors.append(
                    "Original Character collection destroyed"
                )
            else:
                if (live_ptr != original_ptr
                        or _find_live_collection_by_identity(col, original_ptr) is None):
                    restoration_errors.append(
                        "Character collection original live identity changed"
                    )
                else:
                    # Only snapshot-proven hierarchy edges may be restored.
                    if orig_name is not None and col.name != orig_name:
                        col.name = orig_name

                    if char_col_snap.get("children_of_scene", False):
                        scene = bpy.context.scene if bpy.context else None
                        if scene is None:
                            restoration_errors.append("Original scene root unavailable for Character collection")
                        else:
                            scene_root = scene.collection
                            _authorized_restore_snapshot_collection_child(
                                scene_root, scene_root.as_pointer(), col, original_ptr,
                                restoration_errors,
                            )

                    expected_parents = char_col_snap.get("parent_refs", [])
                    expected_parent_ptrs = char_col_snap.get("parent_ptrs", [])
                    if len(expected_parents) != len(expected_parent_ptrs):
                        restoration_errors.append("Character parent snapshot refs/pointers length mismatch")
                    else:
                        for parent, parent_ptr in zip(expected_parents, expected_parent_ptrs):
                            _authorized_restore_snapshot_collection_child(
                                parent, parent_ptr, col, original_ptr, restoration_errors,
                            )

                    expected_children = char_col_snap.get("child_refs", [])
                    expected_child_ptrs = char_col_snap.get("child_ptrs", [])
                    if len(expected_children) != len(expected_child_ptrs):
                        restoration_errors.append("Character child snapshot refs/pointers length mismatch")
                    else:
                        for child, child_ptr in zip(expected_children, expected_child_ptrs):
                            _authorized_restore_snapshot_collection_child(
                                col, original_ptr, child, child_ptr, restoration_errors,
                            )

                    # Member Objects restoration by reference via Layer 3
                    expected_refs = char_col_snap.get(
                        "object_refs", []
                    )

                    for obj in expected_refs:
                        try:
                            obj_ptr = obj.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Character collection original member was destroyed"
                            )
                            continue

                        _authorized_ensure_snapshot_collection_link(
                            col,
                            obj,
                            obj_ptr,
                            restoration_errors,
                        )

    _depsgraph_update()

    if restoration_errors:
        raise RuntimeError("Rollback constraint restoration failed: " + "; ".join(restoration_errors))


def _verify_arm_rig_state_restored(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Verify that current Arm IK rig state precisely matches the snapshot.

    Raises:
        RuntimeError: If any discrepancy is detected between current state and snapshot.
    """
    current = _snapshot_arm_rig_state(arm)
    diffs: List[str] = []
    TOL = 1e-5

    def _vec_diff(v1, v2) -> float:
        return max(abs(a - b) for a, b in zip(v1, v2))

    def _quat_diff(q1, q2) -> float:
        d1 = sum((a - b)**2 for a, b in zip(q1, q2))**0.5
        d2 = sum((a + b)**2 for a, b in zip(q1, q2))**0.5
        return min(d1, d2)

    def _mat_diff(m1, m2) -> Tuple[float, int, int]:
        max_d = 0.0
        max_r, max_c = 0, 0
        for r in range(4):
            for c in range(4):
                d = abs(m1[r][c] - m2[r][c])
                if d > max_d:
                    max_d = d
                    max_r, max_c = r, c
        return max_d, max_r, max_c

    # 1. Collection check
    s_col = snapshot.get("character_collection", {})
    c_col = current.get("character_collection", {})

    if s_col.get("existed"):
        if not c_col.get("existed"):
            diffs.append("Character collection existed in snapshot but is missing in current state")
        else:
            # Check original collection object identity
            orig_col_ref = s_col.get("col_ref")
            orig_col_ptr = s_col.get("col_ptr")
            curr_col_ref = c_col.get("col_ref")
            curr_col_ptr = c_col.get("col_ptr")

            if orig_col_ref is not None:
                try:
                    live_col_ptr = orig_col_ref.as_pointer()
                    if orig_col_ptr and live_col_ptr != orig_col_ptr:
                        diffs.append("Character collection original pointer changed")
                except ReferenceError:
                    diffs.append("Character collection original collection destroyed")

            if orig_col_ptr and curr_col_ptr and curr_col_ptr != orig_col_ptr:
                diffs.append(f"Character collection identity mismatch: expected={orig_col_ptr}, actual={curr_col_ptr}")

            if orig_col_ref is not None and s_col.get("name") != c_col.get("name"):
                diffs.append(f"Character collection name '{c_col.get('name')}' != expected '{s_col.get('name')}'")

            # Parent / Child / Member identity hierarchy verification
            if s_col.get("children_of_scene") and not c_col.get("children_of_scene"):
                diffs.append("Character collection missing from scene collection children")

            def _live_identity_set(items, desc: str = "item"):
                result = set()
                for item in items:
                    try:
                        result.add(item.as_pointer())
                    except ReferenceError:
                        diffs.append(f"Character collection original {desc} was destroyed")
                return result

            original_parent_ptrs = _live_identity_set(
                s_col.get("parent_refs", []), "parent collection"
            )
            current_parent_ptrs = _live_identity_set(
                c_col.get("parent_refs", []), "current parent collection"
            )
            missing_parent_ptrs = (
                original_parent_ptrs - current_parent_ptrs
            )
            if missing_parent_ptrs:
                diffs.append(
                    "Character collection original parent "
                    f"identities missing: {missing_parent_ptrs}"
                )

            original_child_ptrs = _live_identity_set(
                s_col.get("child_refs", []), "child collection"
            )
            current_child_ptrs = _live_identity_set(
                c_col.get("child_refs", []), "current child collection"
            )
            missing_child_ptrs = (
                original_child_ptrs - current_child_ptrs
            )
            if missing_child_ptrs:
                diffs.append(
                    "Character collection original child "
                    f"identities missing: {missing_child_ptrs}"
                )

            original_obj_ptrs = _live_identity_set(
                s_col.get("object_refs", []), "member object"
            )
            current_obj_ptrs = _live_identity_set(
                c_col.get("object_refs", []), "current member object"
            )
            missing_obj_ptrs = (
                original_obj_ptrs - current_obj_ptrs
            )
            if missing_obj_ptrs:
                diffs.append(
                    "Character collection original member "
                    f"identities missing: {missing_obj_ptrs}"
                )
    else:
        # Snapshot did NOT have Character collection.
        # If active_tx created it, active_tx.created_collections will catch it below if not removed.
        # If an external party created a Character collection, it must be preserved.
        pass

    # Check that transaction-created collections do not linger
    if active_tx is not None:
        for reg in getattr(active_tx, "created_collections", []):
            c_name = reg.get("created_name")
            c_ptr = reg.get("col_ptr")
            c_ref = reg.get("col_ref")
            found_lingering = False
            if c_ref is not None:
                try:
                    if c_ref.name in bpy.data.collections and bpy.data.collections[c_ref.name] == c_ref:
                        found_lingering = True
                except ReferenceError:
                    found_lingering = False
            if not found_lingering and c_name in bpy.data.collections:
                col_obj = bpy.data.collections[c_name]
                if c_ptr is None or col_obj.as_pointer() == c_ptr:
                    found_lingering = True
            if found_lingering:
                diffs.append(f"Transaction-created collection '{c_name}' still exists in scene")

    # 2. Controllers check
    s_ctrls = snapshot.get("controllers", {})
    c_ctrls = current.get("controllers", {})
    for c_name, sc in s_ctrls.items():
        cc = c_ctrls.get(c_name)
        if cc is None or sc["exists"] != cc["exists"]:
            diffs.append(f"Controller {c_name} exists={getattr(cc, 'get', lambda k: None)('exists')}, expected {sc['exists']}")
            continue
        if not sc["exists"]:
            continue

        try:
            obj_mismatch = (sc["obj_ref"] != cc["obj_ref"])
        except ReferenceError:
            obj_mismatch = True
        if obj_mismatch:
            diffs.append(f"Controller {c_name} obj_ref identity mismatch")
        if sc.get("obj_ptr") and cc.get("obj_ptr") and sc["obj_ptr"] != cc["obj_ptr"]:
            diffs.append(f"Controller {c_name} obj_ptr mismatch: {cc['obj_ptr']} != {sc['obj_ptr']}")
        try:
            data_mismatch = (sc["data_ref"] != cc["data_ref"])
        except ReferenceError:
            data_mismatch = True
        if data_mismatch:
            diffs.append(f"Controller {c_name} data_ref identity mismatch")
        if sc.get("data_ptr") and cc.get("data_ptr") and sc["data_ptr"] != cc["data_ptr"]:
            diffs.append(f"Controller {c_name} data_ptr mismatch: {cc['data_ptr']} != {sc['data_ptr']}")
        if sc["obj_name"] != cc["obj_name"]:
            diffs.append(f"Controller {c_name} obj_name {cc['obj_name']} != {sc['obj_name']}")
        if sc["type"] != cc["type"]:
            diffs.append(f"Controller {c_name} type {cc['type']} != {sc['type']}")
        if sc["parent"] != cc["parent"]:
            diffs.append(f"Controller {c_name} parent {cc['parent']} != {sc['parent']}")

        mat_inv_diff, mr, mc = _mat_diff(sc["matrix_parent_inverse"], cc["matrix_parent_inverse"])
        if mat_inv_diff > TOL:
            diffs.append(f"Controller {c_name} matrix_parent_inverse[{mr}][{mc}] diff {mat_inv_diff:.6e} > {TOL}")

        loc_diff = _vec_diff(sc["location"], cc["location"])
        if loc_diff > TOL:
            diffs.append(f"Controller {c_name} location diff {loc_diff:.6e} > {TOL}")

        if sc["rotation_mode"] != cc["rotation_mode"]:
            diffs.append(f"Controller {c_name} rotation_mode {cc['rotation_mode']} != {sc['rotation_mode']}")

        euler_diff = _vec_diff(sc["rotation_euler"], cc["rotation_euler"])
        if euler_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_euler diff {euler_diff:.6e} > {TOL}")

        quat_diff = _quat_diff(sc["rotation_quaternion"], cc["rotation_quaternion"])
        if quat_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_quaternion diff {quat_diff:.6e} > {TOL}")

        d_angle = abs(sc["rotation_axis_angle"][0] - cc["rotation_axis_angle"][0])
        d_axis = _vec_diff(sc["rotation_axis_angle"][1:], cc["rotation_axis_angle"][1:])
        axis_diff = max(d_angle, d_axis)
        if axis_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_axis_angle diff {axis_diff:.6e} > {TOL}")

        scale_diff = _vec_diff(sc["scale"], cc["scale"])
        if scale_diff > TOL:
            diffs.append(f"Controller {c_name} scale diff {scale_diff:.6e} > {TOL}")

        mat_w_diff, wr, wc = _mat_diff(sc["matrix_world"], cc["matrix_world"])
        if mat_w_diff > TOL:
            diffs.append(f"Controller {c_name} matrix_world[{wr}][{wc}] diff {mat_w_diff:.6e} > {TOL}")

        if set(sc["collections"]) != set(cc["collections"]):
            diffs.append(f"Controller {c_name} collections {cc['collections']} != {sc['collections']}")

        if sc["type"] == "EMPTY":
            if sc["empty_display_type"] != cc["empty_display_type"]:
                diffs.append(f"Controller {c_name} empty_display_type {cc['empty_display_type']} != {sc['empty_display_type']}")
            if abs(sc["empty_display_size"] - cc["empty_display_size"]) > TOL:
                diffs.append(f"Controller {c_name} empty_display_size {cc['empty_display_size']} != {sc['empty_display_size']}")

    # 3. Pose bones check
    s_bones = snapshot.get("pose_bones", {})
    c_bones = current.get("pose_bones", {})
    for b_name, sb in s_bones.items():
        cb = c_bones.get(b_name)
        if cb is None:
            diffs.append(f"Pose bone {b_name} missing in current state")
            continue

        loc_diff = _vec_diff(sb["location"], cb["location"])
        if loc_diff > TOL:
            diffs.append(f"Bone {b_name} location diff {loc_diff:.6e} > {TOL}")

        if sb["rotation_mode"] != cb["rotation_mode"]:
            diffs.append(f"Bone {b_name} rotation_mode {cb['rotation_mode']} != {sb['rotation_mode']}")

        euler_diff = _vec_diff(sb["rotation_euler"], cb["rotation_euler"])
        if euler_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_euler diff {euler_diff:.6e} > {TOL}")

        quat_diff = _quat_diff(sb["rotation_quaternion"], cb["rotation_quaternion"])
        if quat_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_quaternion diff {quat_diff:.6e} > {TOL}")

        d_angle = abs(sb["rotation_axis_angle"][0] - cb["rotation_axis_angle"][0])
        d_axis = _vec_diff(sb["rotation_axis_angle"][1:], cb["rotation_axis_angle"][1:])
        axis_diff = max(d_angle, d_axis)
        if axis_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_axis_angle diff {axis_diff:.6e} > {TOL}")

        scale_diff = _vec_diff(sb["scale"], cb["scale"])
        if scale_diff > TOL:
            diffs.append(f"Bone {b_name} scale diff {scale_diff:.6e} > {TOL}")

        basis_diff, br, bc = _mat_diff(sb["matrix_basis"], cb["matrix_basis"])
        if basis_diff > TOL:
            diffs.append(f"Bone {b_name} matrix_basis[{br}][{bc}] diff {basis_diff:.6e} > {TOL}")

        for axis in ("x", "y", "z"):
            if sb[f"lock_ik_{axis}"] != cb[f"lock_ik_{axis}"]:
                diffs.append(f"Bone {b_name} lock_ik_{axis} {cb[f'lock_ik_{axis}']} != {sb[f'lock_ik_{axis}']}")
            if sb[f"use_ik_limit_{axis}"] != cb[f"use_ik_limit_{axis}"]:
                diffs.append(f"Bone {b_name} use_ik_limit_{axis} {cb[f'use_ik_limit_{axis}']} != {sb[f'use_ik_limit_{axis}']}")
            if abs(sb[f"ik_min_{axis}"] - cb[f"ik_min_{axis}"]) > TOL:
                diffs.append(f"Bone {b_name} ik_min_{axis} {cb[f'ik_min_{axis}']} != {sb[f'ik_min_{axis}']}")
            if abs(sb[f"ik_max_{axis}"] - cb[f"ik_max_{axis}"]) > TOL:
                diffs.append(f"Bone {b_name} ik_max_{axis} {cb[f'ik_max_{axis}']} != {sb[f'ik_max_{axis}']}")

        # Constraints
        sc_list = sb["constraints"]
        cc_list = cb["constraints"]

        # Check that transaction-created constraints do not linger
        if active_tx is not None:
            for reg_con in getattr(active_tx, "created_constraints", []):
                if reg_con.get("bone_name") == b_name:
                    expected_ptr = reg_con.get("con_ptr")
                    for c in cc_list:
                        if c.get("con_ptr") == expected_ptr:
                            diffs.append(
                                f"Bone {b_name} transaction-created constraint "
                                f"'{reg_con.get('created_name')}' still present after rollback"
                            )

        # Map current live constraints by pointer
        cc_by_ptr = {c.get("con_ptr"): c for c in cc_list if c.get("con_ptr")}
        orig_ptrs = [sc["con_ptr"] for sc in sc_list if sc.get("con_ptr")]

        # Verify each original constraint is restored
        for idx, sc in enumerate(sc_list):
            orig_con = sc.get("con_ref")
            orig_ptr = sc.get("con_ptr")
            label = f"Bone {b_name} constraint[{idx}] '{sc['name']}'"

            if orig_con is None or orig_ptr is None:
                diffs.append(f"{label}: snapshot identity missing")
                continue

            try:
                live_orig_ptr = orig_con.as_pointer()
            except ReferenceError:
                diffs.append(f"{label}: original constraint destroyed")
                continue

            if live_orig_ptr != orig_ptr:
                diffs.append(f"{label}: original pointer changed")
                continue

            cc = cc_by_ptr.get(orig_ptr)
            if cc is None:
                diffs.append(f"{label}: identity mismatch: original constraint destroyed or absent from live chain")
                continue

            curr_con = cc.get("con_ref")
            curr_ptr = cc.get("con_ptr")
            if curr_con is None or curr_ptr is None:
                diffs.append(f"{label}: current identity missing")
                continue

            if curr_ptr != orig_ptr:
                diffs.append(
                    f"{label}: identity mismatch; "
                    f"expected={orig_ptr}, "
                    f"actual={curr_ptr}"
                )

            if sc["name"] != cc["name"]:
                diffs.append(f"{label} name {cc['name']} != {sc['name']}")
            if sc["type"] != cc["type"]:
                diffs.append(f"{label} type {cc['type']} != {sc['type']}")
            if abs(sc["influence"] - cc["influence"]) > TOL:
                diffs.append(f"{label} influence {cc['influence']} != {sc['influence']}")
            if sc["mute"] != cc["mute"]:
                diffs.append(f"{label} mute {cc['mute']} != {sc['mute']}")
            if sc.get("target") != cc.get("target"):
                diffs.append(f"{label} target {cc.get('target')} != {sc.get('target')}")
            if sc.get("subtarget") != cc.get("subtarget"):
                diffs.append(f"{label} subtarget {cc.get('subtarget')} != {sc.get('subtarget')}")
            if sc.get("pole_target") != cc.get("pole_target"):
                diffs.append(f"{label} pole_target {cc.get('pole_target')} != {sc.get('pole_target')}")
            if sc.get("pole_subtarget") != cc.get("pole_subtarget"):
                diffs.append(f"{label} pole_subtarget {cc.get('pole_subtarget')} != {sc.get('pole_subtarget')}")

            if sc["type"] == "IK":
                if sc.get("chain_count") != cc.get("chain_count"):
                    diffs.append(f"{label} chain_count {cc.get('chain_count')} != {sc.get('chain_count')}")
                if sc.get("use_tail") != cc.get("use_tail"):
                    diffs.append(f"{label} use_tail {cc.get('use_tail')} != {sc.get('use_tail')}")
                if sc.get("use_stretch") != cc.get("use_stretch"):
                    diffs.append(f"{label} use_stretch {cc.get('use_stretch')} != {sc.get('use_stretch')}")
                if abs(sc.get("pole_angle", 0.0) - cc.get("pole_angle", 0.0)) > TOL:
                    diffs.append(f"{label} pole_angle {cc.get('pole_angle')} != {sc.get('pole_angle')}")
                if sc.get("iterations") != cc.get("iterations"):
                    diffs.append(f"{label} iterations {cc.get('iterations')} != {sc.get('iterations')}")
            elif sc["type"] == "COPY_ROTATION":
                if sc.get("target_space") != cc.get("target_space"):
                    diffs.append(f"{label} target_space {cc.get('target_space')} != {sc.get('target_space')}")
                if sc.get("owner_space") != cc.get("owner_space"):
                    diffs.append(f"{label} owner_space {cc.get('owner_space')} != {sc.get('owner_space')}")
                if sc.get("mix_mode") != cc.get("mix_mode"):
                    diffs.append(f"{label} mix_mode {cc.get('mix_mode')} != {sc.get('mix_mode')}")
                for axis in ("x", "y", "z"):
                    if sc.get(f"use_{axis}") != cc.get(f"use_{axis}"):
                        diffs.append(f"{label} use_{axis} {cc.get(f'use_{axis}')} != {sc.get(f'use_{axis}')}")
                    if sc.get(f"invert_{axis}") != cc.get(f"invert_{axis}"):
                        diffs.append(f"{label} invert_{axis} {cc.get(f'invert_{axis}')} != {sc.get(f'invert_{axis}')}")
                if sc.get("use_offset") != cc.get("use_offset"):
                    diffs.append(f"{label} use_offset {cc.get('use_offset')} != {sc.get('use_offset')}")

            # Check generic properties
            s_gen = sc.get("generic_props", {})
            c_gen = cc.get("generic_props", {})
            for g_prop, s_val in s_gen.items():
                c_val = c_gen.get(g_prop)
                if isinstance(s_val, (Vector, Euler)):
                    if c_val is None or _vec_diff(s_val, c_val) > TOL:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")
                elif isinstance(s_val, Quaternion):
                    if c_val is None or _quat_diff(s_val, c_val) > TOL:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")
                elif isinstance(s_val, tuple):
                    if c_val is None or not hasattr(c_val, "__len__") or len(c_val) != len(s_val):
                        diffs.append(f"{label} {g_prop} length mismatch: {c_val} != {s_val}")
                    else:
                        for arr_i, (sv, cv) in enumerate(zip(s_val, c_val)):
                            if isinstance(sv, float):
                                if abs(sv - cv) > TOL:
                                    diffs.append(f"{label} {g_prop}[{arr_i}] {cv} != {sv} (diff {abs(sv - cv):.6e} > {TOL})")
                            elif sv != cv:
                                diffs.append(f"{label} {g_prop}[{arr_i}] {cv} != {sv}")
                elif isinstance(s_val, float):
                    if c_val is None or abs(s_val - c_val) > TOL:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")
                else:
                    if s_val != c_val:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")

        # Check relative ordering of original constraints
        orig_live_indices = []
        for sc in sc_list:
            sc_ptr = sc.get("con_ptr")
            for c_idx, cc in enumerate(cc_list):
                if cc.get("con_ptr") == sc_ptr:
                    orig_live_indices.append(c_idx)
                    break
        if orig_live_indices != sorted(orig_live_indices):
            diffs.append(
                f"Bone {b_name} original constraints relative order violated: "
                f"indices={orig_live_indices}"
            )

        # In standalone check without transaction context, constraint count must match exactly
        if active_tx is None and len(sc_list) != len(cc_list):
            diffs.append(f"Bone {b_name} constraint count {len(cc_list)} != {len(sc_list)}")

    # 4. Active transaction stack check
    if active_tx is None:
        if len(_ACTIVE_TRANSACTION_STACK) != 0:
            diffs.append(f"Active transaction stack is not empty (contains {len(_ACTIVE_TRANSACTION_STACK)} transactions)")
    else:
        if _ACTIVE_TRANSACTION_STACK != [active_tx]:
            diffs.append(f"Active transaction stack contains unexpected transactions: {_ACTIVE_TRANSACTION_STACK}")

    # 5. Relationship operation log terminal state verification (Task 10-B-11)
    if active_tx is not None:
        for op_rec in getattr(active_tx, "prepared_relationship_mutations", []):
            op_id = op_rec.get("operation_id", "<unknown>")
            op_state = op_rec.get("operation_state")
            if op_state == _RelationshipOperationState.RECOVERY_UNCERTAIN:
                diffs.append(
                    f"Relationship operation '{op_id}' is in RECOVERY_UNCERTAIN state after rollback"
                )
            elif op_state not in (
                _RelationshipOperationState.NO_EFFECT,
                _RelationshipOperationState.REVERTED,
            ):
                diffs.append(
                    f"Relationship operation '{op_id}' did not reach a valid rollback terminal state "
                    f"(expected NO_EFFECT or REVERTED, got {op_state})"
                )

    if diffs:
        raise RuntimeError("Arm rig rollback verification failed: " + "; ".join(diffs))



# BUG-10: the only positive Type-A DataBlock authority issuer.
# It physically creates the Mesh before minting a transaction-bound receipt.
def _authorized_create_type_a_mesh(name: str, active_tx: Any) -> bpy.types.Mesh:
    """Create a transaction-owned Mesh with an identity-bound deletion receipt.

    Only this creation-returned Blender ID can receive TYPE_A_TX_CREATED
    authority. Observing an existing ID or appending an authorization dict
    never proves transaction creation.
    """
    if type(name) is not str or not name.strip():
        raise ValueError("TYPE_A_CREATE_DENIED: Mesh name must be nonempty")
    if (active_tx is None or not _ACTIVE_TRANSACTION_STACK
            or _ACTIVE_TRANSACTION_STACK[-1] is not active_tx
            or active_tx.state != _ArmRigTransactionState.ACTIVE):
        raise RuntimeError("TYPE_A_CREATE_DENIED: owning ACTIVE transaction required")
    if (not isinstance(active_tx._type_a_datablock_receipts, dict)
            or not isinstance(active_tx.datablock_authorizations, list)
            or active_tx.session_record is None
            or _MANAGED_ARMATURE_IDENTITIES.get(active_tx.session_id) is not active_tx.session_record
            or active_tx.session_record.original_blender_ref is not active_tx.arm):
        raise RuntimeError("TYPE_A_CREATE_DENIED: transaction provenance/ledger invalid")
    before = frozenset(int(item.as_pointer()) for item in bpy.data.meshes)
    mesh = bpy.data.meshes.new(name)
    new_ptr = None
    auth = None
    receipt_registered = False
    try:
        new_ptr = int(mesh.as_pointer())
        if (new_ptr <= 0 or new_ptr in before
                or new_ptr in active_tx._type_a_datablock_receipts
                or not any(int(item.as_pointer()) == new_ptr and item == mesh
                           for item in bpy.data.meshes)
                or int(mesh.users) != 0):
            raise RuntimeError("TYPE_A_CREATE_DENIED: fresh Mesh identity is unproven")
        active_tx._type_a_datablock_receipts[new_ptr] = (
            mesh, active_tx.session_id, active_tx.tx_id,
            active_tx._type_a_datablock_receipt_seal,
        )
        receipt_registered = True
        auth = {
            "resource_kind": "meshes",
            "original_reference": mesh,
            "original_pointer": new_ptr,
            "provenance": "TYPE_A_TX_CREATED",
            "authorization_source": "TX_CREATE_RECEIPT",
            "authorization_scope": "PHYSICAL_DELETE_IF_ZERO_USERS",
            "authorized_transaction": active_tx.tx_id,
            "expected_lifecycle": "COMMITTED_CLEANUP",
        }
        active_tx.datablock_authorizations.append(auth)
        return mesh
    except BaseException as creation_exc:
        # Compensate only the same newly-created zero-user ID. Never use name
        # matching or a pointer that existed before this creation call.
        cleanup_exc = None
        try:
            if receipt_registered and new_ptr is not None:
                receipt = active_tx._type_a_datablock_receipts.get(new_ptr)
                if receipt is not None and receipt[0] == mesh:
                    active_tx._type_a_datablock_receipts.pop(new_ptr, None)
            if auth is not None and auth in active_tx.datablock_authorizations:
                active_tx.datablock_authorizations.remove(auth)
            if (new_ptr is None or new_ptr in before or new_ptr <= 0
                    or int(mesh.as_pointer()) != new_ptr
                    or int(mesh.users) != 0
                    or not any(int(item.as_pointer()) == new_ptr and item == mesh
                               for item in bpy.data.meshes)):
                raise RuntimeError("TYPE_A_CREATE_CLEANUP_UNPROVEN: refusing deletion")
            bpy.data.meshes.remove(mesh, do_unlink=False)
            if any(int(item.as_pointer()) == new_ptr for item in bpy.data.meshes):
                raise RuntimeError("TYPE_A_CREATE_CLEANUP_FAILED: Mesh remains live")
        except BaseException as exc:
            cleanup_exc = exc
        if cleanup_exc is not None:
            raise RuntimeError(
                "TYPE_A_CREATE_AND_CLEANUP_FAILED: "
                f"original={type(creation_exc).__name__}: {creation_exc}; "
                f"cleanup={type(cleanup_exc).__name__}: {cleanup_exc}"
            ) from cleanup_exc
        raise

class _ArmRigTransactionContext:
    """Active transaction execution state tracking."""

    def __init__(
        self,
        arm: bpy.types.Object,
        session_record: Optional[ArmatureSessionIdentityRecord] = None,
    ):
        _layer2_initialize_arm_rig_transaction_context(
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
        return _layer2_prepare_relationship_mutation(
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
        return _layer2_update_relationship_mutation_state(
            self,
            op_record,
            new_state,
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
        return _layer2_register_created_controller(
            self,
            obj,
            find_live_object_by_identity=(
                _find_live_object_by_identity
            ),
            controller_role_for_name=(
                _controller_role_for_name
            ),
        )


    # [INTRODUCED 2026-11-16T17:18:48+08:00]
    # FUNCTION: _ArmRigTransactionContext.register_created_constraint
    # PURPOSE: Enforce receipt verification and active transaction ownership before registering created constraints
    # REASON: Task 10-B fix-4, prevent unauthorized direct registration without independent creation receipt
    def register_created_constraint(
        self,
        pbone: bpy.types.PoseBone,
        con: bpy.types.Constraint,
    ) -> None:
        """Register a constraint created by this transaction for identity-based ownership."""
        return _layer2_register_created_constraint(
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
        return _layer2_register_created_collection_link(
            self,
            col,
            obj,
        )

    def register_created_collection(
        self,
        col: bpy.types.Collection,
        initial_parent: Optional[bpy.types.Collection] = None,
    ) -> None:
        """Attest a newly created, not-yet-linked Collection and intended parent."""
        return _layer2_register_created_collection(
            self,
            col,
            initial_parent=initial_parent,
            find_live_collection_by_identity=(
                _find_live_collection_by_identity
            ),
        )

    def retry_cleanup(self) -> _CleanupResult:
        """Idempotently retry irreversible cleanup of pending stashed resources."""
        if self.state in (
            _ArmRigTransactionState.FAILED,
            _ArmRigTransactionState.ROLLING_BACK,
            _ArmRigTransactionState.ROLLED_BACK,
            _ArmRigTransactionState.ACTIVE,
            _ArmRigTransactionState.SNAPSHOTTING,
            _ArmRigTransactionState.CREATED,
        ):
            raise RuntimeError(
                f"Cannot execute retry_cleanup on transaction {self.tx_id} in state {self.state}: "
                f"FAILED -> COMMITTED transition is strictly forbidden"
            )
        cleanup_failures: List[str] = []
        first_cause: Optional[BaseException] = None

        # ------------------------------------------------------
        # Task 10-B-8
        # Identity-safe cleanup of stashed constraints
        # ------------------------------------------------------

        for stashed_con in list(self.uncleaned_stashed_constraints):
            try:
                pbone = stashed_con.get("pbone")
                _authorized_remove_constraint(
                    pbone=pbone,
                    con_record_or_ref=stashed_con,
                    phase="POST_COMMIT_CLEANUP",
                    active_tx=self,
                )
                self.uncleaned_stashed_constraints.remove(stashed_con)
            except Exception as exc:
                if first_cause is None:
                    first_cause = exc
                cleanup_failures.append(
                    "Failed to clean up stashed constraint "
                    f"{stashed_con.get('orig_name')}: {exc}"
                )

        # 2. Clean up stashed doomed objects and unreferenced datablocks
        for stashed in list(self.uncleaned_stashed_objects):
            # Step 2.1: Object cleanup
            if not stashed.get("obj_cleaned", False):
                try:
                    _trigger_fault_injection("during_cleanup_object_removal", {"stashed": stashed})
                    obj_ref = stashed.get("stashed_obj")
                    obj_ptr = stashed.get("stashed_obj_ptr")

                    target_obj = None
                    for o in bpy.data.objects:
                        try:
                            if obj_ptr and o.as_pointer() == obj_ptr:
                                target_obj = o
                                break
                            elif obj_ref is not None and o == obj_ref:
                                target_obj = o
                                break
                        except ReferenceError:
                            continue

                    if target_obj is not None:
                        bpy.data.objects.remove(target_obj, do_unlink=True)
                        still_exists = any(
                            (obj_ptr and o.as_pointer() == obj_ptr)
                            for o in bpy.data.objects
                        )
                        if still_exists:
                            cleanup_failures.append(
                                f"Failed to delete doomed object {stashed.get('original_name')}: still exists in bpy.data.objects"
                            )
                        else:
                            stashed["obj_cleaned"] = True
                    else:
                        stashed["obj_cleaned"] = True
                except Exception as oe:
                    if first_cause is None:
                        first_cause = oe
                    cleanup_failures.append(f"Failed to clean up stashed object {stashed.get('original_name')}: {oe}")

            # Step 2.2: DataBlock cleanup (runs only if object cleanup has succeeded)
            if stashed.get("obj_cleaned", False) and not stashed.get("data_cleaned", False):
                try:
                    _trigger_fault_injection("during_cleanup_datablock_removal", {"stashed": stashed})
                    data_ref = stashed.get("stashed_data")
                    data_ptr = stashed.get("stashed_data_ptr")
                    data_name = stashed.get("stashed_data_name")

                    if data_ptr is None and data_ref is None:
                        stashed["data_cleaned"] = True
                    else:
                        target_data = None
                        target_coll = None
                        for coll_name in ("meshes", "curves", "lights", "cameras", "armatures", "lattices", "metaballs", "volumes"):
                            coll = getattr(bpy.data, coll_name, None)
                            if coll is not None:
                                for item in coll:
                                    try:
                                        if data_ptr and item.as_pointer() == data_ptr:
                                            target_data = item
                                            target_coll = coll
                                            break
                                        elif data_ref is not None and item == data_ref:
                                            target_data = item
                                            target_coll = coll
                                            break
                                    except ReferenceError:
                                        continue
                            if target_data is not None:
                                break

                        if target_data is None:
                            stashed["data_cleaned"] = True
                            stashed["data_cleanup_status"] = "DATA_ALREADY_ABSENT"
                        else:
                            # Step 1: Check independent DataBlock deletion authorization
                            matching_auth = None
                            for auth in self.datablock_authorizations:
                                if not isinstance(auth, dict):
                                    continue
                                if auth.get("authorized_transaction") != self.tx_id:
                                    continue
                                auth_ptr = auth.get("original_pointer")
                                auth_ref = auth.get("original_reference")
                                if (auth_ptr is not None and auth_ptr == data_ptr) or (auth_ref is not None and auth_ref == target_data):
                                    matching_auth = auth
                                    break

                            if matching_auth is None:
                                # Step 1.1: No authorization -> preserve datablock without deletion
                                stashed["data_cleanup_status"] = "PRESERVED_NO_DELETE_AUTHORITY"
                                stashed["data_cleaned"] = True
                                already_recorded = any(
                                    (o.get("resource_pointer") == data_ptr or (data_ref is not None and o.get("original_reference") == data_ref))
                                    and o.get("tx_id") == self.tx_id
                                    for o in self.datablock_cleanup_outcomes
                                )
                                if not already_recorded:
                                    self.datablock_cleanup_outcomes.append({
                                        "action": "PRESERVED",
                                        "status": "PRESERVED_NO_DELETE_AUTHORITY",
                                        "reason": "NO_DELETE_AUTHORITY",
                                        "resource_kind": getattr(target_coll, "name", type(target_data).__name__),
                                        "resource_name": data_name,
                                        "resource_pointer": data_ptr,
                                        "original_reference": data_ref,
                                        "tx_id": self.tx_id,
                                    })
                            else:
                                # Step 2: Strictly validate 12 conditions (Fail-Closed)
                                required_fields = (
                                    "resource_kind",
                                    "original_reference",
                                    "original_pointer",
                                    "provenance",
                                    "authorization_source",
                                    "authorization_scope",
                                    "authorized_transaction",
                                    "expected_lifecycle",
                                )
                                missing_fields = [f for f in required_fields if f not in matching_auth]
                                if missing_fields:
                                    raise RuntimeError(f"DataBlock authorization for {data_name} missing fields: {missing_fields}")

                                if matching_auth["authorized_transaction"] != self.tx_id:
                                    raise RuntimeError(f"DataBlock authorization tx mismatch: {matching_auth['authorized_transaction']} != {self.tx_id}")

                                if matching_auth.get("authorization_scope") != "PHYSICAL_DELETE_IF_ZERO_USERS":
                                    raise RuntimeError(f"DataBlock authorization scope invalid: {matching_auth.get('authorization_scope')}")

                                provenance = matching_auth.get("provenance")
                                if provenance not in ("TYPE_A_TX_CREATED", "TYPE_B_PRE_EXISTING_EXPLICIT_GRANT"):
                                    raise RuntimeError(f"DataBlock deletion authorization provenance rejected: {provenance}")

                                if provenance == "TYPE_A_TX_CREATED":
                                    # Positive Type-A path: authorization comes from
                                    # this transaction's actual Mesh creation call,
                                    # never from a free-form claim or name.
                                    receipt = self._type_a_datablock_receipts.get(data_ptr)
                                    if (not isinstance(receipt, tuple) or len(receipt) != 4
                                            or receipt[0] != target_data
                                            or receipt[1] != self.session_id
                                            or receipt[2] != self.tx_id
                                            or receipt[3] is not self._type_a_datablock_receipt_seal
                                            or matching_auth.get("authorization_source") != "TX_CREATE_RECEIPT"
                                            or matching_auth.get("resource_kind") != "meshes"
                                            or matching_auth.get("original_reference") != target_data
                                            or matching_auth.get("original_pointer") != data_ptr
                                            or not any(int(item.as_pointer()) == data_ptr and item == target_data
                                                       for item in bpy.data.meshes)):
                                        raise RuntimeError(
                                            f"DataBlock {data_name} claims TYPE_A_TX_CREATED but lacks credible transaction creation provenance"
                                        )
                                elif provenance == "TYPE_B_PRE_EXISTING_EXPLICIT_GRANT":
                                    raise RuntimeError(
                                        f"DATA_BLOCK_DELETE_AUTHORITY_UNPROVEN: {data_name}: "
                                        "TYPE_B deletion requires verified authorization "
                                        "from a trusted issuer; authorization_source "
                                        "string is not sufficient proof"
                                    )

                                orig_ref = matching_auth.get("original_reference")
                                if orig_ref is None:
                                    raise RuntimeError(f"DataBlock authorization original_reference is None")
                                try:
                                    _ = getattr(orig_ref, "name")
                                except Exception as ref_err:
                                    raise RuntimeError(f"DataBlock original_reference is invalid or dead: {ref_err}")

                                try:
                                    live_ptr = target_data.as_pointer()
                                except Exception as ptr_err:
                                    raise RuntimeError(f"Fail-closed: failed to read live pointer for {data_name}: {ptr_err}")

                                if matching_auth.get("original_pointer") != live_ptr:
                                    raise RuntimeError(f"DataBlock original_pointer mismatch: {matching_auth.get('original_pointer')} != {live_ptr}")
                                if data_ptr is not None and data_ptr != live_ptr:
                                    raise RuntimeError(f"DataBlock stashed pointer mismatch: {data_ptr} != {live_ptr}")

                                if target_coll is None:
                                    raise RuntimeError(f"DataBlock {data_name} collection not found in bpy.data")
                                try:
                                    item_in_coll = any(item.as_pointer() == live_ptr for item in target_coll)
                                except Exception as coll_err:
                                    raise RuntimeError(f"Fail-closed: failed to enumerate collection for {data_name}: {coll_err}")
                                if not item_in_coll:
                                    raise RuntimeError(f"DataBlock {data_name} does not exist in collection {target_coll}")

                                if orig_ref != target_data:
                                    raise RuntimeError(f"DataBlock current live reference does not match original_reference")

                                try:
                                    user_count = target_data.users
                                except Exception as u_err:
                                    raise RuntimeError(f"Fail-closed: failed to read users attribute on {data_name}: {u_err}")
                                if user_count != 0:
                                    raise RuntimeError(f"DataBlock {data_name} cannot be deleted: users count is {user_count} > 0")

                                try:
                                    fake_user = target_data.use_fake_user
                                except Exception as fu_err:
                                    raise RuntimeError(f"Fail-closed: failed to read use_fake_user attribute on {data_name}: {fu_err}")
                                if fake_user is not False:
                                    raise RuntimeError(f"DataBlock {data_name} has use_fake_user == True; cannot delete")

                                try:
                                    lib = target_data.library
                                except Exception as lib_err:
                                    raise RuntimeError(f"Fail-closed: failed to read library attribute on {data_name}: {lib_err}")
                                if lib is not None:
                                    raise RuntimeError(f"DataBlock {data_name} belongs to library {lib}; cannot delete")

                                try:
                                    if hasattr(target_data, "override_library") and target_data.override_library is not None:
                                        raise RuntimeError(f"DataBlock {data_name} has override_library; cannot delete")
                                except AttributeError:
                                    pass
                                except Exception as dep_err:
                                    raise RuntimeError(f"Fail-closed: failed checking external dependencies on {data_name}: {dep_err}")

                                # BUG-11: fault windows bracket physical DataBlock deletion
                                # AFTER all existing authorization/dependency checks pass.
                                # This adds no bypass, no alternate deletion path.
                                _trigger_fault_injection(
                                    "during_cleanup_datablock_after_auth_before_remove",
                                    {"stashed": stashed, "data_ptr": data_ptr,
                                     "data": target_data, "tx": self},
                                )
                                target_coll.remove(target_data, do_unlink=False)
                                _trigger_fault_injection(
                                    "during_cleanup_datablock_after_remove_before_verify",
                                    {"stashed": stashed, "data_ptr": data_ptr,
                                     "tx": self},
                                )

                                still_present = False
                                try:
                                    still_present = any(
                                        (data_ptr and item.as_pointer() == data_ptr)
                                        for item in target_coll
                                    )
                                except Exception:
                                    still_present = True

                                if still_present:
                                    raise RuntimeError(f"Failed to delete datablock {data_name}: still exists in {target_coll}")
                                else:
                                    stashed["data_cleaned"] = True
                                    stashed["data_cleanup_status"] = "PHYSICALLY_DELETED"
                                    already_recorded = any(
                                        (o.get("resource_pointer") == data_ptr or (data_ref is not None and o.get("original_reference") == data_ref))
                                        and o.get("tx_id") == self.tx_id
                                        for o in self.datablock_cleanup_outcomes
                                    )
                                    if not already_recorded:
                                        self.datablock_cleanup_outcomes.append({
                                            "action": "DELETED",
                                            "status": "PHYSICALLY_DELETED",
                                            "reason": "AUTHORIZED_CLEANUP",
                                            "resource_kind": getattr(target_coll, "name", type(target_data).__name__),
                                            "resource_name": data_name,
                                            "resource_pointer": data_ptr,
                                            "tx_id": self.tx_id,
                                        })
                except Exception as de:
                    if first_cause is None:
                        first_cause = de
                    cleanup_failures.append(f"Failed to clean up datablock for {stashed.get('original_name')}: {de}")

            # Only remove record from uncleaned_stashed_objects when BOTH object and datablock are cleaned
            if stashed.get("obj_cleaned", False) and stashed.get("data_cleaned", False):
                if stashed in self.uncleaned_stashed_objects:
                    self.uncleaned_stashed_objects.remove(stashed)

        rem_objs = len(self.uncleaned_stashed_objects)
        rem_cons = len(self.uncleaned_stashed_constraints)
        err_tuple = tuple(cleanup_failures)

        if not err_tuple and rem_objs == 0 and rem_cons == 0:
            outcome = _CleanupOutcome.CLEANUP_SUCCESS
            self.cleanup_error = None
        elif rem_objs > 0 or rem_cons > 0:
            outcome = _CleanupOutcome.CLEANUP_INCOMPLETE
            self.cleanup_error = "; ".join(err_tuple) if err_tuple else "Cleanup incomplete: remaining stashed resources"
        else:
            outcome = _CleanupOutcome.CLEANUP_FAILED
            self.cleanup_error = "; ".join(err_tuple) if err_tuple else "Cleanup result unprovable or failed"

        return _CleanupResult(
            transaction_id=self.tx_id,
            outcome=outcome,
            errors=err_tuple,
            remaining_objects=rem_objs,
            remaining_constraints=rem_cons,
            cause=first_cause,
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
    if phase not in ("INITIAL_CLEANUP", "PENDING_RETRY"):
        raise ValueError(f"Invalid cleanup preflight phase: {phase!r}")
    if not isinstance(tx, _ArmRigTransactionContext):
        raise RuntimeError("CLEANUP_PREFLIGHT_REJECTED: transaction context type is invalid")
    if not isinstance(tx.tx_id, str) or not tx.tx_id:
        raise RuntimeError("CLEANUP_PREFLIGHT_REJECTED: missing transaction ID")

    expected_state = (
        _ArmRigTransactionState.COMMITTED
        if phase == "INITIAL_CLEANUP"
        else _ArmRigTransactionState.CLEANUP_PENDING
    )
    if tx.state != expected_state:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: transaction {tx.tx_id} "
            f"is {tx.state}, expected {expected_state}"
        )

    if _ACTIVE_TRANSACTION_STACK:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: active transaction stack is nonempty "
            f"during {phase}"
        )

    registered_pending = _PENDING_ARM_RIG_CLEANUPS.get(tx.tx_id)
    if phase == "PENDING_RETRY":
        if registered_pending is not tx:
            raise RuntimeError(
                "CLEANUP_PREFLIGHT_REJECTED: pending registry transaction "
                f"identity mismatch for {tx.tx_id}"
            )
    elif registered_pending is not None:
        raise RuntimeError(
            "CLEANUP_PREFLIGHT_REJECTED: initial cleanup transaction "
            f"{tx.tx_id} already exists in the pending registry"
        )

    # Check both registry provenance and Blender's current object identity.
    # Never call ensure_armature_session_identity() here: it can register a new
    # session, which is not a valid substitute for the transaction's original.
    record = tx.session_record
    session_id = tx.session_id
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("CLEANUP_PREFLIGHT_REJECTED: missing original session ID")
    if record is None or _MANAGED_ARMATURE_IDENTITIES.get(session_id) is not record:
        raise RuntimeError(
            "CLEANUP_PREFLIGHT_REJECTED: original session registry record "
            f"not found or substituted for {tx.tx_id}"
        )
    if record.registry_session_id != session_id or record.original_blender_ref is not tx.arm:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: session and original Armature provenance "
            f"mismatch for {tx.tx_id}"
        )
    try:
        live_ptr = int(tx.arm.as_pointer())
    except BaseException as exc:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: cannot read original Armature identity "
            f"for {tx.tx_id}: {exc}"
        ) from exc
    if live_ptr != tx.arm_ptr or live_ptr != record.registration_pointer:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: original Armature pointer mismatch "
            f"for {tx.tx_id}"
        )
    try:
        identity_check = _verify_armature_session_identity_record(record, candidate_arm=tx.arm)
    except BaseException as exc:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: Armature identity verification raised "
            f"for {tx.tx_id}: {exc}"
        ) from exc
    if identity_check.get("is_valid") is not True:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: original Armature session not verified "
            f"for {tx.tx_id}: {identity_check.get('reasons', [])}"
        )

    if (record.isolation_state != _ArmatureIsolationState.NONE
            or session_id in _ISOLATED_FAILED_ARMATURES):
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: transaction {tx.tx_id} "
            f"is associated with active FAILED isolation"
        )
    # Also defend against a malformed isolation registry record whose key is
    # different from the transaction's session ID, but whose tx_id matches.
    for isolation in _ISOLATED_FAILED_ARMATURES.values():
        if isolation.get("transaction_id") == tx.tx_id:
            raise RuntimeError(
                f"CLEANUP_PREFLIGHT_REJECTED: transaction {tx.tx_id} "
                "is referenced by FAILED isolation under another registry key"
            )

    if (not isinstance(tx.uncleaned_stashed_objects, list)
            or not isinstance(tx.uncleaned_stashed_constraints, list)
            or any(not isinstance(entry, dict) for entry in tx.uncleaned_stashed_objects)
            or any(not isinstance(entry, dict) for entry in tx.uncleaned_stashed_constraints)):
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: cleanup resource queue is malformed "
            f"for {tx.tx_id}"
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
    if phase not in ("INITIAL_CLEANUP", "PENDING_RETRY"):
        raise ValueError(f"Invalid cleanup decision phase: {phase!r}")
    if not isinstance(tx, _ArmRigTransactionContext):
        raise RuntimeError("Coordinator rejected cleanup result: invalid transaction context")
    if not isinstance(result, _CleanupResult):
        raise RuntimeError(
            f"Coordinator rejected cleanup result: expected _CleanupResult instance, got {type(result)}"
        )
    if not isinstance(tx.tx_id, str) or not tx.tx_id:
        raise RuntimeError("Coordinator rejected cleanup result: missing transaction_id")
    if not isinstance(result.transaction_id, str) or result.transaction_id != tx.tx_id:
        raise RuntimeError(
            f"Coordinator rejected cleanup result: transaction_id mismatch "
            f"({result.transaction_id!r} != {tx.tx_id!r})"
        )
    expected_state = (
        _ArmRigTransactionState.COMMITTED
        if phase == "INITIAL_CLEANUP"
        else _ArmRigTransactionState.CLEANUP_PENDING
    )
    if tx.state != expected_state:
        raise RuntimeError(
            f"Coordinator rejected cleanup result: phase {phase} requires "
            f"state {expected_state.value}, got {tx.state}"
        )
    if type(result.outcome) is not _CleanupOutcome:
        raise RuntimeError(
            f"Coordinator rejected cleanup result: invalid CleanupOutcome {result.outcome!r}"
        )
    for label, count in (
        ("remaining_objects", result.remaining_objects),
        ("remaining_constraints", result.remaining_constraints),
    ):
        if type(count) is not int or count < 0:
            raise RuntimeError(
                f"Coordinator rejected cleanup result: {label} must be a nonnegative int, got {count!r}"
            )
    if not isinstance(result.errors, tuple) or any(
        not isinstance(message, str) or not message.strip()
        for message in result.errors
    ):
        raise RuntimeError(
            "Coordinator rejected cleanup result: errors must be a tuple of nonempty strings"
        )
    if result.cause is not None and not isinstance(result.cause, BaseException):
        raise RuntimeError(
            "Coordinator rejected cleanup result: cause must be BaseException or None"
        )
    if not isinstance(tx.uncleaned_stashed_objects, list) or not isinstance(
        tx.uncleaned_stashed_constraints, list
    ):
        raise RuntimeError("Coordinator rejected cleanup result: malformed cleanup queues")
    actual_rem_objs = len(tx.uncleaned_stashed_objects)
    actual_rem_cons = len(tx.uncleaned_stashed_constraints)
    if (result.remaining_objects != actual_rem_objs
            or result.remaining_constraints != actual_rem_cons):
        raise RuntimeError(
            "Coordinator rejected cleanup result: remaining resource count mismatch "
            f"(reported: objs={result.remaining_objects}, cons={result.remaining_constraints}; "
            f"actual: objs={actual_rem_objs}, cons={actual_rem_cons})"
        )
    remaining = result.remaining_objects + result.remaining_constraints
    if result.outcome == _CleanupOutcome.CLEANUP_SUCCESS:
        if result.errors:
            raise RuntimeError(
                f"Coordinator rejected cleanup result: CLEANUP_SUCCESS cannot carry errors: {result.errors}"
            )
        if remaining:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_SUCCESS cannot have remaining resources "
                f"(objs={result.remaining_objects}, cons={result.remaining_constraints})"
            )
        if result.cause is not None:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_SUCCESS cannot carry a cause"
            )
    elif result.outcome == _CleanupOutcome.CLEANUP_INCOMPLETE:
        if remaining == 0:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_INCOMPLETE requires remaining resources"
            )
    elif result.outcome == _CleanupOutcome.CLEANUP_FAILED:
        if remaining != 0 or not result.errors:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_FAILED requires "
                "zero remaining resources and at least one error"
            )
    else:
        raise RuntimeError("Coordinator rejected cleanup result: unsupported outcome")


def _coordinator_preserve_cleanup_pending(
    tx: "_ArmRigTransactionContext",
    error: BaseException,
) -> None:
    """Fail closed after logical commit without clobbering another transaction.

    Used by the initial cleanup exception paths. Never changes FAILED to
    COMMITTED/PENDING, never removes a FAILED isolation, and never pops a gate.
    In an impossible registry-key collision, raise rather than overwrite it.
    """
    if not isinstance(tx, _ArmRigTransactionContext):
        raise RuntimeError("CLEANUP_PENDING_REGISTRATION_FAILED: invalid context") from error
    if tx.state not in (
        _ArmRigTransactionState.COMMITTED,
        _ArmRigTransactionState.CLEANUP_PENDING,
    ):
        raise RuntimeError(
            f"CLEANUP_PENDING_REGISTRATION_FAILED: transaction {tx.tx_id} "
            f"cannot move from {tx.state} into CLEANUP_PENDING"
        ) from error
    if not isinstance(tx.tx_id, str) or not tx.tx_id:
        raise RuntimeError("CLEANUP_PENDING_REGISTRATION_FAILED: invalid transaction ID") from error
    existing = _PENDING_ARM_RIG_CLEANUPS.get(tx.tx_id)
    if existing is not None and existing is not tx:
        raise RuntimeError(
            f"CLEANUP_PENDING_REGISTRATION_FAILED: registry collision for {tx.tx_id}; "
            "foreign transaction preserved"
        ) from error
    if existing is tx and tx.state == _ArmRigTransactionState.CLEANUP_PENDING:
        return
    tx.state = _ArmRigTransactionState.CLEANUP_PENDING
    tx.cleanup_error = f"{type(error).__name__}: {error}"
    if existing is None:
        _register_pending_arm_rig_cleanup(tx)
    if _PENDING_ARM_RIG_CLEANUPS.get(tx.tx_id) is not tx:
        raise RuntimeError(
            f"CLEANUP_PENDING_REGISTRATION_FAILED: transaction {tx.tx_id} not registered"
        ) from error


def _coordinator_apply_cleanup_result(
    tx: "_ArmRigTransactionContext",
    result: "_CleanupResult",
    phase: str,
) -> None:
    """Exclusively decide cleanup state after full result/identity validation.

    No malformed result, uncertain Armature, or FAILED isolation may be treated
    as success; rejection is reported, not swallowed or coerced to NO_EFFECT.
    """
    _coordinator_validate_cleanup_result_contract(tx, result, phase)

    if _ACTIVE_TRANSACTION_STACK:
        raise RuntimeError(
            "Coordinator rejected cleanup result: active transaction stack must be empty"
        )
    # Verify original registry provenance, not a newly generated replacement
    # session from ensure_armature_session_identity().
    session_id = tx.session_id
    record = tx.session_record
    if (not isinstance(session_id, str) or not session_id
            or record is None
            or _MANAGED_ARMATURE_IDENTITIES.get(session_id) is not record
            or record.registry_session_id != session_id):
        raise RuntimeError(
            "Coordinator rejected cleanup result: session_id mismatch or original session record unavailable"
        )
    if record.original_blender_ref is not tx.arm:
        raise RuntimeError(
            "Coordinator rejected cleanup result: original Armature reference mismatch"
        )
    try:
        pointer = int(tx.arm.as_pointer())
    except BaseException as exc:
        raise RuntimeError(
            "Coordinator rejected cleanup result: original Armature identity unreadable"
        ) from exc
    if pointer != tx.arm_ptr or pointer != record.registration_pointer:
        raise RuntimeError(
            "Coordinator rejected cleanup result: original Armature pointer mismatch"
        )
    try:
        identity_check = _verify_armature_session_identity_record(record, candidate_arm=tx.arm)
    except BaseException as exc:
        raise RuntimeError(
            "Coordinator rejected cleanup result: Armature identity verification raised"
        ) from exc
    if identity_check.get("is_valid") is not True:
        raise RuntimeError(
            "Coordinator rejected cleanup result: Armature identity unverified: "
            f"{identity_check.get('reasons', [])}"
        )

    registered = _PENDING_ARM_RIG_CLEANUPS.get(tx.tx_id)
    if phase == "PENDING_RETRY":
        if registered is not tx:
            raise RuntimeError(
                "Coordinator rejected cleanup result: transaction "
                f"{tx.tx_id} identity mismatch or absent in _PENDING_ARM_RIG_CLEANUPS"
            )
    elif registered is not None:
        raise RuntimeError(
            "Coordinator rejected cleanup result: unexpected pending registry entry "
            f"for initial cleanup {tx.tx_id}"
        )

    # Any FAILED isolation of this Armature blocks a cleanup-result decision.
    # ALSO reject an isolation record under a corrupted/mis-keyed session entry.
    # No try/except here: an identity or isolation read error MUST propagate.
    if (record.isolation_state != _ArmatureIsolationState.NONE
            or session_id in _ISOLATED_FAILED_ARMATURES):
        raise RuntimeError(
            f"Coordinator rejected cleanup result: active FAILED isolation for session {session_id}"
        )
    for isolated in _ISOLATED_FAILED_ARMATURES.values():
        if isolated.get("transaction_id") == tx.tx_id:
            raise RuntimeError(
                "Coordinator rejected cleanup result: transaction "
                f"{tx.tx_id} associated with FAILED isolation under another key"
            )

    if result.outcome is _CleanupOutcome.CLEANUP_SUCCESS:
        # Recheck the exact registry entry BEFORE any lifecycle mutation.
        if phase == "PENDING_RETRY" and _PENDING_ARM_RIG_CLEANUPS.get(tx.tx_id) is not tx:
            raise RuntimeError(
                "Coordinator rejected cleanup result: pending registry changed before release"
            )
        tx.cleanup_error = None
        tx.state = _ArmRigTransactionState.COMMITTED
        if phase == "PENDING_RETRY":
            _PENDING_ARM_RIG_CLEANUPS.pop(tx.tx_id)
        return

    # Non-success outcome: keep gate, preserve original traceback in __cause__.
    err_msg = (
        f"Arm rig transaction commit cleanup {result.outcome.value}: "
        f"transaction={tx.tx_id}; phase={phase}; "
        f"remaining_objects={result.remaining_objects}; "
        f"remaining_constraints={result.remaining_constraints}; "
        f"errors={'; '.join(result.errors)}"
    )
    _coordinator_preserve_cleanup_pending(tx, RuntimeError(err_msg))
    tx.cleanup_error = "; ".join(result.errors) if result.errors else "Cleanup incomplete or failed"
    if result.cause is not None:
        raise RuntimeError(err_msg) from result.cause
    raise RuntimeError(err_msg)


def _register_pending_arm_rig_cleanup(
    tx: "_ArmRigTransactionContext",
) -> None:

    if tx.state != _ArmRigTransactionState.CLEANUP_PENDING:
        raise RuntimeError(
            "Cannot register cleanup for "
            "a non-pending transaction"
        )

    _PENDING_ARM_RIG_CLEANUPS[tx.tx_id] = tx


def get_pending_arm_rig_cleanup_ids() -> Tuple[str, ...]:
    """Return pending cleanup transaction IDs."""

    return tuple(
        sorted(_PENDING_ARM_RIG_CLEANUPS)
    )


def retry_pending_arm_rig_cleanup(tx_id: str) -> None:
    """Retry cleanup of one pending transaction."""

    tx = _PENDING_ARM_RIG_CLEANUPS.get(tx_id)

    if tx is None:
        for iso_rec in _ISOLATED_FAILED_ARMATURES.values():
            if iso_rec.get("transaction_id") == tx_id:
                raise RuntimeError(
                    f"Cannot retry cleanup for FAILED transaction {tx_id}: "
                    "FAILED transactions cannot be recovered via retry_pending_arm_rig_cleanup "
                    "or transition FAILED -> COMMITTED"
                )
        raise KeyError(
            f"Pending cleanup transaction not found: {tx_id}"
        )

    if tx.state == _ArmRigTransactionState.FAILED:
        raise RuntimeError(
            f"Transaction {tx_id} is in FAILED state; "
            "FAILED -> COMMITTED transition is strictly forbidden"
        )

    if tx.state != _ArmRigTransactionState.CLEANUP_PENDING:
        raise RuntimeError(
            f"Transaction {tx_id} is in state {tx.state}, expected CLEANUP_PENDING for pending cleanup retry"
        )

    _coordinator_validate_cleanup_preflight(tx, phase="PENDING_RETRY")
    cleanup_result = tx.retry_cleanup()
    _coordinator_apply_cleanup_result(tx, cleanup_result, phase="PENDING_RETRY")


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

    session_rec: Optional[ArmatureSessionIdentityRecord] = None
    if session_id is not None:
        session_rec = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
    elif arm is not None:
        for rec in _MANAGED_ARMATURE_IDENTITIES.values():
            if rec.original_blender_ref is arm:
                session_rec = rec
                break
            if rec.liveness_status == _ArmatureLivenessStatus.ALIVE_VERIFIED:
                ver = _verify_armature_session_identity_record(rec, candidate_arm=arm)
                if ver["is_valid"]:
                    session_rec = rec
                    break

    resolved_session_id = session_rec.registry_session_id if session_rec is not None else session_id
    arm_ptr = _safe_object_pointer(
        arm,
        fallback=(session_rec.registration_pointer if session_rec is not None else 0),
    )

    pending_cleanup_txs = [
        tx_id
        for tx_id, tx in _PENDING_ARM_RIG_CLEANUPS.items()
        if (arm_ptr and tx.arm_ptr == arm_ptr)
        or (resolved_session_id is not None and getattr(tx, "session_id", None) == resolved_session_id)
    ]
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(resolved_session_id) if resolved_session_id else None
    archived_rec = _ARCHIVED_FAILED_D_TOMBSTONES.get(resolved_session_id) if resolved_session_id else None

    id_check = (
        _verify_armature_session_identity_record(session_rec, candidate_arm=arm)
        if session_rec is not None
        else {"is_valid": False, "reasons": ["Session record not registered"]}
    )

    cleanup_blocked = len(pending_cleanup_txs) > 0
    failed_isolated = bool(
        iso_rec is not None
        or (
            session_rec is not None
            and session_rec.isolation_state != _ArmatureIsolationState.NONE
        )
    )
    identity_valid = bool(id_check["is_valid"])

    return {
        "registry_session_id": resolved_session_id,
        "cleanup_pending_blocked": cleanup_blocked,
        "pending_cleanup_transaction_ids": sorted(pending_cleanup_txs),
        "failed_isolation_blocked": failed_isolated,
        "failure_class": (
            iso_rec.get("failure_class")
            if iso_rec is not None
            else (archived_rec.get("failure_class") if archived_rec is not None else None)
        ),
        "isolation_state": (
            session_rec.isolation_state.value
            if session_rec is not None
            else None
        ),
        "liveness_status": (
            session_rec.liveness_status.value
            if session_rec is not None
            else None
        ),
        "identity_valid": identity_valid,
        "identity_reasons": id_check.get("reasons", []),
        "can_admit": (not cleanup_blocked and not failed_isolated and identity_valid),
    }


def verify_armature_deisolation_evidence(
    arm: Optional[bpy.types.Object] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Layer 5: Read-only verification of recovery evidence before de-isolating an Armature (Section 8.2)."""
    _sweep_dead_managed_armature_identities()

    session_rec: Optional[ArmatureSessionIdentityRecord] = None
    if session_id is not None:
        session_rec = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
    elif arm is not None:
        for rec in _MANAGED_ARMATURE_IDENTITIES.values():
            if rec.original_blender_ref is arm:
                session_rec = rec
                break
            if rec.liveness_status == _ArmatureLivenessStatus.ALIVE_VERIFIED:
                ver = _verify_armature_session_identity_record(rec, candidate_arm=arm)
                if ver["is_valid"]:
                    session_rec = rec
                    break

    resolved_session_id = session_rec.registry_session_id if session_rec is not None else session_id
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(resolved_session_id) if resolved_session_id else None
    archived_rec = _ARCHIVED_FAILED_D_TOMBSTONES.get(resolved_session_id) if resolved_session_id else None

    if session_rec is None or (iso_rec is None and archived_rec is None):
        return {
            "can_deisolate": False,
            "status": "NOT_ISOLATED",
            "case": "NONE",
            "registry_session_id": resolved_session_id,
            "failure_class": None,
            "isolation_state": (session_rec.isolation_state.value if session_rec is not None else None),
            "reasons": ["Armature session is not present in _ISOLATED_FAILED_ARMATURES"],
        }

    if archived_rec is not None or session_rec.isolation_state == _ArmatureIsolationState.ARCHIVED_RETIRED:
        return {
            "can_deisolate": False,
            "status": "REJECTED_ARCHIVED_TOMBSTONE",
            "case": "CASE_3_DEAD_TOMBSTONE",
            "registry_session_id": resolved_session_id,
            "failure_class": _FailedTransactionClass.FAILED_D.value,
            "isolation_state": _ArmatureIsolationState.ARCHIVED_RETIRED.value,
            "reasons": ["FAILED-D tombstone is already ARCHIVED_RETIRED and cannot return to active status"],
        }

    failure_class = iso_rec.get("failure_class")
    target_arm = arm if arm is not None else session_rec.original_blender_ref
    id_ver = _verify_armature_session_identity_record(session_rec, candidate_arm=target_arm)

    # Case 3: FAILED-D or dead Armature tombstone
    if (
        failure_class == _FailedTransactionClass.FAILED_D.value
        or session_rec.isolation_state == _ArmatureIsolationState.TOMBSTONED_FAILED_D
        or session_rec.liveness_status == _ArmatureLivenessStatus.INVALIDATED_DEAD
    ):
        reasons = [
            "FAILED-D dead Armature tombstone cannot be restored to active status; "
            "use retire_dead_armature_tombstone after verifying residual resources"
        ]
        if not id_ver["is_valid"]:
            reasons.extend(id_ver["reasons"])
        return {
            "can_deisolate": False,
            "status": "REJECTED_DEAD_ARMATURE_TOMBSTONE",
            "case": "CASE_3_DEAD_TOMBSTONE",
            "registry_session_id": resolved_session_id,
            "failure_class": failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "reasons": reasons,
        }

    # Case 2: No trusted pre-transaction snapshot available
    snapshot = iso_rec.get("snapshot_reference")
    snapshot_trusted = bool(iso_rec.get("snapshot_trusted", False) and snapshot is not None)
    if not snapshot_trusted:
        missing_reasons = list(
            iso_rec.get("missing_evidence_reasons")
            or ["Trusted pre-transaction snapshot is missing; recovery evidence is insufficient"]
        )
        return {
            "can_deisolate": False,
            "status": "RECOVERY_EVIDENCE_INSUFFICIENT",
            "case": "CASE_2_NO_TRUSTED_SNAPSHOT",
            "registry_session_id": resolved_session_id,
            "failure_class": failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "reasons": missing_reasons,
        }

    # Case 1: Trusted snapshot exists -> verify all 8 mandatory conditions simultaneously
    reasons: List[str] = []

    # Condition 1: 7-condition ArmatureSessionIdentityRecord verification
    if not id_ver["is_valid"]:
        reasons.extend(id_ver["reasons"])

    # Condition 7 (checked before snapshot restore call because _verify_arm_rig_state_restored also checks stack):
    # _ACTIVE_TRANSACTION_STACK is empty
    if len(_ACTIVE_TRANSACTION_STACK) != 0:
        reasons.append(
            f"Active transaction stack is not empty (contains {len(_ACTIVE_TRANSACTION_STACK)} active transaction(s))"
        )

    # Condition 2: Current Armature, Controllers, PoseBones, Constraints, and Collections match snapshot 100%
    if id_ver["is_valid"] and target_arm is not None:
        try:
            _verify_arm_rig_state_restored(target_arm, snapshot, active_tx=None)
        except BaseException as ver_exc:
            reasons.append(f"Snapshot state verification failed: {ver_exc}")

    # Condition 3: No transaction-created Controllers remain in bpy.data.objects by identity
    for ctrl_rec in iso_rec.get("created_controller_objects", []):
        c_ref = ctrl_rec.get("obj_ref")
        c_ptr = ctrl_rec.get("obj_ptr")
        c_name = ctrl_rec.get("created_name", "<unknown>")
        if c_ptr is not None and _find_live_object_by_identity(c_ref, c_ptr) is not None:
            reasons.append(f"Transaction-created controller '{c_name}' (ptr={c_ptr}) still exists in bpy.data.objects")

    # Condition 4: No transaction-created Constraints remain on any PoseBone by identity
    if id_ver["is_valid"] and target_arm is not None and getattr(target_arm, "pose", None) is not None:
        for con_rec in iso_rec.get("created_constraints", []):
            b_name = con_rec.get("bone_name")
            con_ptr = con_rec.get("con_ptr")
            con_name = con_rec.get("created_name", "<unknown>")
            pbone = target_arm.pose.bones.get(b_name) if b_name else None
            if pbone is not None and con_ptr is not None:
                for live_con in pbone.constraints:
                    try:
                        if live_con.as_pointer() == con_ptr:
                            reasons.append(
                                f"Transaction-created constraint '{con_name}' (ptr={con_ptr}) still exists on bone '{b_name}'"
                            )
                            break
                    except ReferenceError:
                        continue

    # Condition 5: No transaction-created Collections remain in bpy.data.collections by identity
    for col_rec in iso_rec.get("created_collections", []):
        col_ref = col_rec.get("col_ref")
        col_ptr = col_rec.get("col_ptr")
        col_name = col_rec.get("created_name", "<unknown>")
        if _find_live_collection_by_identity(col_ref, col_ptr) is not None:
            reasons.append(
                f"Transaction-created collection '{col_name}' (ptr={col_ptr}) still exists in bpy.data.collections"
            )

    # Condition 6: Relationship operation log contains no unverified RECOVERY_UNCERTAIN residual relationships
    for op_rec in iso_rec.get("prepared_relationship_mutations", []):
        op_id = op_rec.get("operation_id", "<unknown>")
        op_state = op_rec.get("operation_state")
        if op_state == _RelationshipOperationState.RECOVERY_UNCERTAIN:
            reasons.append(
                f"Relationship operation '{op_id}' remains in unverified RECOVERY_UNCERTAIN state"
            )
        elif op_state not in (
            _RelationshipOperationState.NO_EFFECT,
            _RelationshipOperationState.REVERTED,
        ):
            reasons.append(
                f"Relationship operation '{op_id}' is in non-terminal rollback state '{op_state}'"
            )

    # Condition 8: No unresolved CLEANUP_PENDING records for this Armature
    pending_cleanups = [
        c_tx_id
        for c_tx_id, c_tx in _PENDING_ARM_RIG_CLEANUPS.items()
        if c_tx.arm_ptr == session_rec.registration_pointer
        or getattr(c_tx, "session_id", None) == resolved_session_id
    ]
    if pending_cleanups:
        reasons.append(
            f"Unresolved CLEANUP_PENDING transaction(s) exist for this Armature: {sorted(pending_cleanups)}"
        )

    can_deisolate = len(reasons) == 0
    return {
        "can_deisolate": can_deisolate,
        "status": "RECOVERY_VERIFIED" if can_deisolate else "RECOVERY_VERIFICATION_FAILED",
        "case": "CASE_1_SNAPSHOT_VERIFIED",
        "registry_session_id": resolved_session_id,
        "transaction_id": iso_rec.get("transaction_id"),
        "failure_class": failure_class,
        "isolation_state": session_rec.isolation_state.value,
        "reasons": reasons,
    }


def _verify_dead_armature_tombstone_retirement_evidence(session_id: str) -> Dict[str, Any]:
    """Layer 5: Read-only verification of dead Armature tombstone retirement conditions (Section 8.2 Case 3)."""
    _sweep_dead_managed_armature_identities()

    session_rec = _MANAGED_ARMATURE_IDENTITIES.get(session_id)
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(session_id)

    if session_rec is None or iso_rec is None:
        return {
            "can_retire": False,
            "status": "TOMBSTONE_NOT_FOUND",
            "registry_session_id": session_id,
            "reasons": [f"Active FAILED-D tombstone for session '{session_id}' not found"],
        }

    reasons: List[str] = []

    if (
        iso_rec.get("failure_class") != _FailedTransactionClass.FAILED_D.value
        or session_rec.isolation_state != _ArmatureIsolationState.TOMBSTONED_FAILED_D
    ):
        reasons.append(
            f"Session '{session_id}' is not a FAILED-D tombstone "
            f"(failure_class={iso_rec.get('failure_class')}, isolation_state={session_rec.isolation_state})"
        )

    # 1. Confirm original Armature is genuinely absent from live Blender objects
    # (Never mistake a same-name replacement Armature for the original,
    # and NEVER mistake data invalidation on an existing Armature for object death)
    obj_liveness = _check_original_object_liveness(session_rec)
    if obj_liveness["status"] != "ABSENT":
        if obj_liveness["status"] == "UNKNOWN":
            reasons.append(
                f"OBJECT_EXISTENCE_UNVERIFIED: Cannot verify absence of original Armature "
                f"(ptr={session_rec.registration_pointer}, status=UNKNOWN); cannot retire tombstone"
            )
        else:
            reasons.append(
                f"Original Armature object still exists in bpy.data.objects (ptr={session_rec.registration_pointer}); "
                "cannot retire tombstone"
            )
    elif session_rec.in_live_blender_collection:
        reasons.append(
            f"Original Armature object still marked as present in live collection (ptr={session_rec.registration_pointer}); "
            "cannot retire tombstone"
        )

    # 2. Confirm no transaction-created objects or collections from the failed transaction remain in bpy.data
    for ctrl_rec in iso_rec.get("created_controller_objects", []):
        c_ref = ctrl_rec.get("obj_ref")
        c_ptr = ctrl_rec.get("obj_ptr")
        c_name = ctrl_rec.get("created_name", "<unknown>")
        if c_ptr is not None and _find_live_object_by_identity(c_ref, c_ptr) is not None:
            reasons.append(
                f"Residual transaction-created controller '{c_name}' (ptr={c_ptr}) still exists in bpy.data.objects"
            )

    for col_rec in iso_rec.get("created_collections", []):
        col_ref = col_rec.get("col_ref")
        col_ptr = col_rec.get("col_ptr")
        col_name = col_rec.get("created_name", "<unknown>")
        if _find_live_collection_by_identity(col_ref, col_ptr) is not None:
            reasons.append(
                f"Residual transaction-created collection '{col_name}' (ptr={col_ptr}) still exists in bpy.data.collections"
            )

    # 3. Confirm no unresolved CLEANUP_PENDING records remain for this session
    pending_cleanups = [
        c_tx_id
        for c_tx_id, c_tx in _PENDING_ARM_RIG_CLEANUPS.items()
        if getattr(c_tx, "session_id", None) == session_id
        or c_tx.arm_ptr == session_rec.registration_pointer
    ]
    if pending_cleanups:
        reasons.append(
            f"Unresolved CLEANUP_PENDING transaction(s) remain for dead Armature session: {sorted(pending_cleanups)}"
        )

    # 4. Confirm _ACTIVE_TRANSACTION_STACK is empty
    if len(_ACTIVE_TRANSACTION_STACK) != 0:
        reasons.append("Active transaction stack is not empty")

    can_retire = len(reasons) == 0
    return {
        "can_retire": can_retire,
        "status": "TOMBSTONE_RETIREMENT_VERIFIED" if can_retire else "TOMBSTONE_RETIREMENT_REJECTED",
        "registry_session_id": session_id,
        "transaction_id": iso_rec.get("transaction_id"),
        "failure_class": iso_rec.get("failure_class"),
        "isolation_state": session_rec.isolation_state.value,
        "reasons": reasons,
    }


def request_armature_deisolation(
    arm: Optional[bpy.types.Object],
    reason: str,
    session_id: Optional[str] = None,
    raise_on_reject: bool = False,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Evaluate Layer 5 evidence and authorize or reject de-isolation (Section 8.1/8.3)."""
    # Enforce non-empty string reason
    if not isinstance(reason, str) or not reason.strip():
        reason_err = "De-isolation rejected: reason must be a non-empty string"
        audit_entry = {
            "audit_id": f"deiso_{uuid.uuid4().hex[:8]}",
            "operation": "REQUEST_DEISOLATION",
            "decision": "REJECTED",
            "registry_session_id": session_id,
            "transaction_id": None,
            "failure_class": None,
            "previous_isolation_state": None,
            "new_isolation_state": None,
            "reason": reason,
            "verification_status": "INVALID_REASON",
            "verification_reasons": [reason_err],
        }
        _append_deisolation_audit(audit_entry)
        if raise_on_reject:
            raise ValueError(reason_err)
        return {
            "approved": False,
            "action": "REJECTED",
            "registry_session_id": session_id,
            "reasons": [reason_err],
            "audit_entry": audit_entry,
        }

    evidence = verify_armature_deisolation_evidence(arm=arm, session_id=session_id)
    resolved_session_id = evidence.get("registry_session_id") or session_id
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(resolved_session_id) if resolved_session_id else None
    tx_id = (
        evidence.get("transaction_id")
        or (iso_rec.get("transaction_id") if iso_rec is not None else None)
    )
    failure_class = evidence.get("failure_class")
    previous_state = evidence.get("isolation_state")

    if evidence.get("can_deisolate", False) and resolved_session_id is not None:
        grant = _issue_coordinator_authorization_grant(
            session_id=resolved_session_id,
            transition_action="CLEAR_TO_NONE",
            arm=arm,
        )
        transition = _clear_or_retire_failure_isolation_by_coordinator(
            session_id=resolved_session_id,
            action="CLEAR_TO_NONE",
            reason=reason,
            authorization_grant=grant,
        )
        audit_entry = {
            "audit_id": f"deiso_{uuid.uuid4().hex[:8]}",
            "operation": "REQUEST_DEISOLATION",
            "decision": "APPROVED",
            "registry_session_id": resolved_session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "previous_isolation_state": previous_state,
            "new_isolation_state": transition["new_isolation_state"],
            "grant_id": grant["grant_id"],
            "reason": reason,
            "verification_status": evidence.get("status"),
            "verification_reasons": list(evidence.get("reasons", [])),
        }
        _append_deisolation_audit(audit_entry)
        return {
            "approved": True,
            "action": "DEISOLATED",
            "registry_session_id": resolved_session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "isolation_state": transition["new_isolation_state"],
            "evidence": evidence,
            "audit_entry": audit_entry,
        }

    audit_entry = {
        "audit_id": f"deiso_{uuid.uuid4().hex[:8]}",
        "operation": "REQUEST_DEISOLATION",
        "decision": "REJECTED",
        "registry_session_id": resolved_session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "previous_isolation_state": previous_state,
        "new_isolation_state": previous_state,
        "reason": reason,
        "verification_status": evidence.get("status"),
        "verification_reasons": list(evidence.get("reasons", [])),
    }
    _append_deisolation_audit(audit_entry)

    if raise_on_reject:
        raise RuntimeError(
            f"Armature de-isolation rejected for session {resolved_session_id} "
            f"(status={evidence.get('status')}): {'; '.join(evidence.get('reasons', []))}"
        )

    return {
        "approved": False,
        "action": "REJECTED",
        "registry_session_id": resolved_session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "isolation_state": previous_state,
        "evidence": evidence,
        "audit_entry": audit_entry,
    }


def retire_dead_armature_tombstone(
    session_id: str,
    reason: str,
    raise_on_reject: bool = False,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Verify dead Armature tombstone retirement evidence and transition to ARCHIVED_RETIRED."""
    # Enforce non-empty string reason
    if not isinstance(reason, str) or not reason.strip():
        reason_err = "Tombstone retirement rejected: reason must be a non-empty string"
        audit_entry = {
            "audit_id": f"retire_{uuid.uuid4().hex[:8]}",
            "operation": "RETIRE_DEAD_TOMBSTONE",
            "decision": "REJECTED",
            "registry_session_id": session_id,
            "transaction_id": None,
            "failure_class": None,
            "previous_isolation_state": None,
            "new_isolation_state": None,
            "reason": reason,
            "verification_status": "INVALID_REASON",
            "verification_reasons": [reason_err],
        }
        _append_deisolation_audit(audit_entry)
        if raise_on_reject:
            raise ValueError(reason_err)
        return {
            "approved": False,
            "action": "REJECTED",
            "registry_session_id": session_id,
            "reasons": [reason_err],
            "audit_entry": audit_entry,
        }

    evidence = _verify_dead_armature_tombstone_retirement_evidence(session_id)
    previous_state = evidence.get("isolation_state")
    tx_id = evidence.get("transaction_id")
    failure_class = evidence.get("failure_class")

    if evidence.get("can_retire", False):
        grant = _issue_coordinator_authorization_grant(
            session_id=session_id,
            transition_action="ARCHIVE_TOMBSTONE",
        )
        transition = _clear_or_retire_failure_isolation_by_coordinator(
            session_id=session_id,
            action="ARCHIVE_TOMBSTONE",
            reason=reason,
            authorization_grant=grant,
        )
        audit_entry = {
            "audit_id": f"retire_{uuid.uuid4().hex[:8]}",
            "operation": "RETIRE_DEAD_TOMBSTONE",
            "decision": "APPROVED",
            "registry_session_id": session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "previous_isolation_state": previous_state,
            "new_isolation_state": transition["new_isolation_state"],
            "grant_id": grant["grant_id"],
            "reason": reason,
            "verification_status": evidence.get("status"),
            "verification_reasons": list(evidence.get("reasons", [])),
        }
        _append_deisolation_audit(audit_entry)
        return {
            "approved": True,
            "action": "ARCHIVED_RETIRED",
            "registry_session_id": session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "isolation_state": transition["new_isolation_state"],
            "evidence": evidence,
            "audit_entry": audit_entry,
        }

    audit_entry = {
        "audit_id": f"retire_{uuid.uuid4().hex[:8]}",
        "operation": "RETIRE_DEAD_TOMBSTONE",
        "decision": "REJECTED",
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "previous_isolation_state": previous_state,
        "new_isolation_state": previous_state,
        "reason": reason,
        "verification_status": evidence.get("status"),
        "verification_reasons": list(evidence.get("reasons", [])),
    }
    _append_deisolation_audit(audit_entry)

    if raise_on_reject:
        raise RuntimeError(
            f"Dead Armature tombstone retirement rejected for session {session_id} "
            f"(status={evidence.get('status')}): {'; '.join(evidence.get('reasons', []))}"
        )

    return {
        "approved": False,
        "action": "REJECTED",
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "isolation_state": previous_state,
        "evidence": evidence,
        "audit_entry": audit_entry,
    }


@contextmanager
def _arm_rig_transaction(arm: bpy.types.Object):
    """Context manager executing Arm IK mutations under atomic transaction protection."""
    global _ACTIVE_TRANSACTION_STACK
    if _ACTIVE_TRANSACTION_STACK:
        outer_tx = _ACTIVE_TRANSACTION_STACK[-1]
        if outer_tx.arm != arm:
            outer_name = _safe_object_name(outer_tx.arm)
            req_name = _safe_object_name(arm)
            raise RuntimeError(
                f"Cross-armature nested transaction rejected: active transaction owns armature "
                f"'{outer_name}', but requested transaction is for armature '{req_name}'."
            )
        if outer_tx.state != _ArmRigTransactionState.ACTIVE:
            raise RuntimeError(
                f"Nested transaction rejected: outer transaction {outer_tx.tx_id} is in state "
                f"{outer_tx.state}, expected ACTIVE."
            )
        if outer_tx.rollback_only:
            raise RuntimeError(
                f"Nested transaction rejected: outer transaction {outer_tx.tx_id} is already marked "
                f"rollback_only ({outer_tx.rollback_only_reason})."
            )
        # Re-entrant invocation on same armature: outer transaction retains exclusive ownership
        try:
            yield outer_tx
        except BaseException as nested_exc:
            outer_tx.mark_rollback_only(f"{type(nested_exc).__name__}: {nested_exc}")
            raise
        return

    # -----------------------------------------------------------------
    # Unified Admission Gate (Section 7):
    # 1. Cleanup Pending Gate -> 2. FAILED Isolation Gate -> 3. Armature Identity Check
    # -----------------------------------------------------------------
    session_rec, admission_id_check = (
        _layer1_admit_outermost_arm_rig_transaction(
            arm,
            ensure_armature_session_identity=ensure_armature_session_identity,
            assert_arm_rig_cleanup_gate=_assert_arm_rig_cleanup_gate,
            assert_arm_rig_failed_isolation_gate=_assert_arm_rig_failed_isolation_gate,
            verify_armature_session_identity_record=_verify_armature_session_identity_record,
        )
    )
    if not admission_id_check["is_valid"]:
        if _identity_failure_is_uncertain(admission_id_check):
            # Admission is before snapshot/business writes. An indeterminate read
            # denies this attempt but does not permanently isolate a healthy rig.
            raise RuntimeError(
                "Arm IK write blocked: ARMATURE_IDENTITY_UNVERIFIED_AT_ADMISSION "
                f"(registry_session_id={session_rec.registry_session_id}): "
                + "; ".join(admission_id_check["reasons"])
            )
        dead_tx = _ArmRigTransactionContext(arm, session_record=session_rec)
        dead_tx.state = _ArmRigTransactionState.FAILED
        _record_armature_failure_isolation_by_coordinator(
            session_rec=session_rec,
            tx=dead_tx,
            failure_class=_FailedTransactionClass.FAILED_D,
            primary_exception=RuntimeError("; ".join(admission_id_check["reasons"])),
            evidence_status="ARMATURE_IDENTITY_INVALID_AT_ADMISSION",
            missing_evidence_reasons=admission_id_check["reasons"],
        )
        raise RuntimeError(
            "Arm IK write blocked: Armature session identity invalid at admission "
            f"(failure_class=FAILED-D, transaction_id={dead_tx.tx_id}, "
            f"registry_session_id={session_rec.registry_session_id}): "
            + "; ".join(admission_id_check["reasons"])
        )

    tx = _layer1_establish_outermost_arm_rig_transaction(
        arm,
        session_rec,
        transaction_context_cls=_ArmRigTransactionContext,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
    )
    pre_snap_fp = None

    try:
        pre_snap_fp = _layer1_capture_transaction_entry_fingerprint(
            arm,
            tx,
            trigger_fault_injection=_trigger_fault_injection,
            capture_pre_snapshot_structural_fingerprint=(
                _capture_pre_snapshot_structural_fingerprint
            ),
        )

        _layer1_snapshot_and_activate_transaction(
            arm,
            tx,
            pre_snap_fp,
            transaction_state_cls=_ArmRigTransactionState,
            snapshot_arm_rig_state=_snapshot_arm_rig_state,
        )

        yield tx

        _layer1_commit_arm_rig_transaction(
            arm,
            tx,
            session_rec,
            transaction_state_cls=_ArmRigTransactionState,
            trigger_fault_injection=_trigger_fault_injection,
            depsgraph_update=_depsgraph_update,
            verify_armature_session_identity_record=(
                _verify_armature_session_identity_record
            ),
        )

    except BaseException as orig_exc:
        # If failure occurred before Phase 2 (Logical Commit), execute classification & rollback!
        if tx.state != _ArmRigTransactionState.COMMITTED:
            if tx.snapshot is not None:
                tx.state = _ArmRigTransactionState.ROLLING_BACK
                rollback_err: Optional[BaseException] = None
                pre_rb_id = _verify_armature_session_identity_record(session_rec, candidate_arm=arm)

                if not pre_rb_id["is_valid"]:
                    # An unverified identity is not a proven-dead Armature.
                    # Never roll back through an uncertain or substituted RNA reference.
                    uncertain = _identity_failure_is_uncertain(pre_rb_id)
                    tx.state = _ArmRigTransactionState.FAILED
                    rollback_err = RuntimeError(
                        "Armature session identity invalidated before rollback "
                        f"(registry_session_id={session_rec.registry_session_id}): "
                        + "; ".join(pre_rb_id["reasons"])
                    )
                    _record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=(_FailedTransactionClass.FAILED_C if uncertain
                                       else _FailedTransactionClass.FAILED_D),
                        primary_exception=orig_exc,
                        secondary_exception=rollback_err,
                        evidence_status=("ARMATURE_IDENTITY_UNVERIFIED_BEFORE_ROLLBACK" if uncertain
                                         else "ARMATURE_DESTROYED_DURING_TRANSACTION"),
                        missing_evidence_reasons=pre_rb_id["reasons"],
                    )
                else:
                    rollback_execution_completed = False
                    try:
                        _rollback_arm_rig_state(arm, tx.snapshot, tx)
                        _depsgraph_update()
                        rollback_execution_completed = True
                        _trigger_fault_injection("during_rollback_verification", {"arm": arm, "tx": tx})
                        _verify_arm_rig_state_restored(arm, tx.snapshot, active_tx=tx)
                        tx.state = _ArmRigTransactionState.ROLLED_BACK
                        session_rec.lifecycle_stage = "NORMAL_TERMINAL"
                    except BaseException as rb_exc:
                        tx.state = _ArmRigTransactionState.FAILED
                        rollback_err = rb_exc
                        post_rb_id = _verify_armature_session_identity_record(session_rec, candidate_arm=arm)
                        if not post_rb_id["is_valid"]:
                            uncertain = _identity_failure_is_uncertain(post_rb_id)
                            f_class = (_FailedTransactionClass.FAILED_C if uncertain
                                       else _FailedTransactionClass.FAILED_D)
                            ev_status = ("ARMATURE_IDENTITY_UNVERIFIED_DURING_ROLLBACK" if uncertain
                                         else "ARMATURE_DESTROYED_DURING_ROLLBACK")
                            ev_reasons = post_rb_id["reasons"]
                        # [INTRODUCED 2026-11-11T22:38:48+08:00]
                        # FUNCTION: _arm_rig_transaction
                        # PURPOSE: Propagate RECOVERY_UNCERTAIN evidence or classify FAILED-C from verified relationship state
                        # REASON: Task 10-B fix-2, TEST-127 / TEST-149
                        elif any(
                            r.get("operation_state") == _RelationshipOperationState.RECOVERY_UNCERTAIN
                            for r in getattr(tx, "prepared_relationship_mutations", [])
                        ):
                            f_class = _FailedTransactionClass.FAILED_C
                            ev_status = "SNAPSHOT_AVAILABLE"
                            ev_reasons = []
                        elif not rollback_execution_completed:
                            f_class = _FailedTransactionClass.FAILED_B
                            ev_status = "SNAPSHOT_AVAILABLE"
                            ev_reasons = []
                        else:
                            f_class = _FailedTransactionClass.FAILED_C
                            ev_status = "SNAPSHOT_AVAILABLE"
                            ev_reasons = []
                        _record_armature_failure_isolation_by_coordinator(
                            session_rec=session_rec,
                            tx=tx,
                            failure_class=f_class,
                            primary_exception=orig_exc,
                            secondary_exception=rb_exc,
                            evidence_status=ev_status,
                            missing_evidence_reasons=ev_reasons,
                        )

                if rollback_err is not None:
                    raise RuntimeError(
                        f"Arm rig transaction failed with {type(orig_exc).__name__}: {orig_exc}, "
                        f"AND rollback verification failed with {type(rollback_err).__name__}: {rollback_err}"
                    ) from orig_exc
                else:
                    raise
            else:
                # Pre-ACTIVE failure (during CREATED or SNAPSHOTTING before snapshot completion)
                tx.state = _ArmRigTransactionState.FAILED
                pre_active_id = _verify_armature_session_identity_record(session_rec, candidate_arm=arm)
                if not pre_active_id["is_valid"]:
                    uncertain = _identity_failure_is_uncertain(pre_active_id)
                    f_class = (_FailedTransactionClass.FAILED_C if uncertain
                               else _FailedTransactionClass.FAILED_D)
                    _record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=f_class,
                        primary_exception=orig_exc,
                        evidence_status=("RECOVERY_EVIDENCE_INSUFFICIENT" if uncertain
                                         else "ARMATURE_DESTROYED_DURING_SNAPSHOTTING"),
                        missing_evidence_reasons=pre_active_id["reasons"],
                    )
                    raise RuntimeError(
                        f"Arm rig transaction failed during SNAPSHOTTING with {type(orig_exc).__name__}: {orig_exc}, "
                        f"AND Armature session identity was invalidated ({f_class.value}, "
                        f"registry_session_id={session_rec.registry_session_id})"
                    ) from orig_exc

                integrity_check = _verify_pre_write_zero_mutation_and_integrity(
                    arm=arm,
                    pre_fp=pre_snap_fp,
                    tx=tx,
                )
                if integrity_check["is_verified"]:
                    # FAILED-A: Pre-write abort with 100% verified zero mutation and intact structure.
                    # Do NOT isolate the healthy Armature!
                    _record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=_FailedTransactionClass.FAILED_A,
                        primary_exception=orig_exc,
                        evidence_status="PRE_WRITE_ZERO_MUTATION_VERIFIED",
                    )
                    raise
                else:
                    # Insufficient evidence to prove zero mutation without a trusted snapshot ->
                    # escalate and isolate as FAILED-C (Section 5.1 & Section 8.2 Case 2).
                    _record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=_FailedTransactionClass.FAILED_C,
                        primary_exception=orig_exc,
                        evidence_status="RECOVERY_EVIDENCE_INSUFFICIENT",
                        missing_evidence_reasons=integrity_check["reasons"],
                    )
                    raise RuntimeError(
                        f"Arm rig transaction failed before ACTIVE with {type(orig_exc).__name__}: {orig_exc}, "
                        "AND pre-write zero-mutation verification failed without a trusted snapshot "
                        f"(classified as FAILED-C, registry_session_id={session_rec.registry_session_id}): "
                        + "; ".join(integrity_check["reasons"])
                    ) from orig_exc
        else:
            raise
    finally:
        _layer1_release_active_arm_rig_transaction(
            tx,
            active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        )

    # -----------------------------------------------------------------
    # Phase 3: Irreversible Resource Cleanup (runs only after logical commit)
    # -----------------------------------------------------------------
    if tx.state == _ArmRigTransactionState.COMMITTED:
        tx.uncleaned_stashed_constraints = list(tx.stashed_constraints)
        tx.uncleaned_stashed_objects = list(tx.stashed_objects)
        try:
            _trigger_fault_injection(
                "after_logical_commit",
                {"tx": tx}
            )
            _trigger_fault_injection(
                "during_commit_cleanup",
                {"tx": tx}
            )
            _coordinator_validate_cleanup_preflight(tx, phase="INITIAL_CLEANUP")
            cleanup_result = tx.retry_cleanup()
        except BaseException as exc:
            _coordinator_preserve_cleanup_pending(tx, exc)
            raise RuntimeError(
                "Arm rig transaction committed, "
                "but post-commit cleanup failed (irreversible cleanup failed): "
                f"{exc}"
            ) from exc

        try:
            _coordinator_apply_cleanup_result(tx, cleanup_result, phase="INITIAL_CLEANUP")
        except BaseException as exc:
            # The resource cleanup has already run. A forged/invalid result or
            # post-cleanup identity failure MUST retain its Pending gate.
            _coordinator_preserve_cleanup_pending(tx, exc)
            raise


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
