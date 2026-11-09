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

ARM_IK_TARGET_NAMES: Dict[str, str] = {"L": "HandIK.L", "R": "HandIK.R"}
ARM_POLE_TARGET_NAMES: Dict[str, str] = {"L": "ElbowPole.L", "R": "ElbowPole.R"}
ARM_IK_CONSTRAINT_NAMES: Dict[str, str] = {"L": "ArmIK.L", "R": "ArmIK.R"}
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


def _validate_influence(val: Any, param_name: str = "influence") -> float:
    """Validate that influence is a finite real number in [0.0, 1.0]."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TypeError(f"'{param_name}' must be a real number, got {type(val).__name__}: {val!r}")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"'{param_name}' must be finite, got: {val!r}")
    if f_val < 0.0 or f_val > 1.0:
        raise ValueError(f"'{param_name}' must be in [0.0, 1.0], got: {val!r}")
    return f_val


def _validate_side(side: Any, allow_both: bool = False, param_name: str = "side") -> str:
    """Validate arm side identifier ('L', 'R', or optionally 'BOTH')."""
    if not isinstance(side, str):
        raise TypeError(f"'{param_name}' must be a string, got {type(side).__name__}: {side!r}")
    s_up = side.strip().upper()
    valid_sides = ("L", "R", "BOTH") if allow_both else ("L", "R")
    if s_up not in valid_sides:
        expected = "'L', 'R', or 'BOTH'" if allow_both else "'L' or 'R'"
        raise ValueError(f"Invalid {param_name} '{side}', expected {expected}")
    return s_up


def _validate_vec3(vec: Any, param_name: str, allow_none: bool = False) -> Optional[Tuple[float, float, float]]:
    """Validate 3-element finite coordinate sequence."""
    if vec is None:
        if allow_none:
            return None
        raise TypeError(f"'{param_name}' cannot be None; expected 3-element sequence of finite numbers")
    if isinstance(vec, (str, bytes, dict)) or not hasattr(vec, "__len__") or not hasattr(vec, "__getitem__"):
        raise TypeError(f"'{param_name}' must be a sequence of 3 finite numbers, got {type(vec).__name__}")
    if len(vec) != 3:
        raise ValueError(f"'{param_name}' must have exactly 3 components, got {len(vec)}: {vec!r}")
    out = []
    for i, comp in enumerate(vec):
        if isinstance(comp, bool) or not isinstance(comp, (int, float)):
            raise TypeError(f"'{param_name}[{i}]' must be a real number, got {type(comp).__name__}: {comp!r}")
        f_comp = float(comp)
        if not math.isfinite(f_comp):
            raise ValueError(f"'{param_name}[{i}]' must be finite, got: {comp!r}")
        out.append(f_comp)
    return (out[0], out[1], out[2])


def _validate_bool(val: Any, param_name: str = "clamp_reach") -> bool:
    """Validate that value is strictly a boolean."""
    if not isinstance(val, bool):
        raise TypeError(f"'{param_name}' must be a boolean (True or False), got {type(val).__name__}: {val!r}")
    return val


def _resolve_armature(armature_obj: Optional[bpy.types.Object] = None) -> bpy.types.Object:
    """Resolve and validate the CharacterArmature object."""
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")
    return armature_obj


def _ensure_character_collection() -> bpy.types.Collection:
    """Ensure the Character collection exists in the active scene."""
    scene = bpy.context.scene
    col = bpy.data.collections.get("Character")
    if col is None:
        col = bpy.data.collections.new("Character")
        scene.collection.children.link(col)
        if _ACTIVE_TRANSACTION_STACK:
            _ACTIVE_TRANSACTION_STACK[-1].register_created_collection(col, initial_parent=scene.collection)
    return col


def _find_collection_by_name(col_name: str) -> Optional[bpy.types.Collection]:
    """Resolve a collection by name across scene master collections and user collections."""
    if bpy.context.scene and bpy.context.scene.collection.name == col_name:
        return bpy.context.scene.collection
    for scene in bpy.data.scenes:
        if scene.collection.name == col_name:
            return scene.collection
    return bpy.data.collections.get(col_name)


# =============================================================================
# Production Transaction Snapshot, Rollback, and Verification Infrastructure
# =============================================================================

class _ArmRigTransactionState(str, Enum):
    """Explicit lifecycle state machine for Arm IK rig transactions."""
    CREATED = "CREATED"
    SNAPSHOTTING = "SNAPSHOTTING"
    ACTIVE = "ACTIVE"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    FAILED = "FAILED"


class _RelationshipOperationState(str, Enum):
    """Explicit 7-state machine for relationship mutation log entries (Task 10-B-11)."""
    PREPARED = "PREPARED"
    APPLYING = "APPLYING"
    APPLIED_VERIFIED = "APPLIED_VERIFIED"
    CONFIRMED = "CONFIRMED"
    NO_EFFECT = "NO_EFFECT"
    REVERTED = "REVERTED"
    RECOVERY_UNCERTAIN = "RECOVERY_UNCERTAIN"


_LEGAL_RELATIONSHIP_LOG_TRANSITIONS: Dict[
    Tuple[_RelationshipOperationState, _RelationshipOperationState], str
] = {
    (_RelationshipOperationState.PREPARED, _RelationshipOperationState.NO_EFFECT): "PREPARED -> NO_EFFECT",
    (_RelationshipOperationState.PREPARED, _RelationshipOperationState.APPLYING): "PREPARED -> APPLYING",
    (_RelationshipOperationState.APPLYING, _RelationshipOperationState.APPLIED_VERIFIED): "APPLYING -> APPLIED_VERIFIED",
    (_RelationshipOperationState.APPLYING, _RelationshipOperationState.NO_EFFECT): "APPLYING -> NO_EFFECT",
    (_RelationshipOperationState.APPLYING, _RelationshipOperationState.RECOVERY_UNCERTAIN): "APPLYING -> RECOVERY_UNCERTAIN",
    (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.CONFIRMED): "APPLIED_VERIFIED -> CONFIRMED",
    (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.REVERTED): "APPLIED_VERIFIED -> REVERTED",
    (_RelationshipOperationState.APPLIED_VERIFIED, _RelationshipOperationState.RECOVERY_UNCERTAIN): "APPLIED_VERIFIED -> RECOVERY_UNCERTAIN",
    (_RelationshipOperationState.CONFIRMED, _RelationshipOperationState.REVERTED): "CONFIRMED -> REVERTED",
    (_RelationshipOperationState.CONFIRMED, _RelationshipOperationState.RECOVERY_UNCERTAIN): "CONFIRMED -> RECOVERY_UNCERTAIN",
}


class _ArmatureLivenessStatus(str, Enum):
    """Explicit liveness status for managed Armature session identities (Task 10-B-13)."""
    ALIVE_VERIFIED = "ALIVE_VERIFIED"
    INVALIDATED_DEAD = "INVALIDATED_DEAD"


class _ArmatureIsolationState(str, Enum):
    """Explicit FAILED isolation state for managed Armature session identities (Task 10-B-13)."""
    NONE = "NONE"
    ISOLATED_FAILED_B = "ISOLATED_FAILED_B"
    ISOLATED_FAILED_C = "ISOLATED_FAILED_C"
    TOMBSTONED_FAILED_D = "TOMBSTONED_FAILED_D"
    ARCHIVED_RETIRED = "ARCHIVED_RETIRED"


class _FailedTransactionClass(str, Enum):
    """Explicit four-class taxonomy for FAILED transactions (Task 10-B-13)."""
    FAILED_A = "FAILED-A"
    FAILED_B = "FAILED-B"
    FAILED_C = "FAILED-C"
    FAILED_D = "FAILED-D"


class ArmatureSessionIdentityRecord:
    """Layer 2 session identity record for a managed Armature (Task 10-B-13)."""

    def __init__(
        self,
        registry_session_id: str,
        original_blender_ref: Optional[bpy.types.Object],
        registration_pointer: int,
        original_data_pointer: int,
        liveness_status: _ArmatureLivenessStatus = _ArmatureLivenessStatus.ALIVE_VERIFIED,
        in_live_blender_collection: bool = True,
        isolation_state: _ArmatureIsolationState = _ArmatureIsolationState.NONE,
        tombstone_record: Optional[Dict[str, Any]] = None,
        original_data_ref: Optional[Any] = None,
        registered_name_snapshot: str = "",
        lifecycle_stage: str = "REGISTERED_ALIVE",
    ) -> None:
        self.registry_session_id: str = str(registry_session_id)
        self.original_blender_ref: Optional[bpy.types.Object] = original_blender_ref
        self.registration_pointer: int = int(registration_pointer)
        self.original_data_pointer: int = int(original_data_pointer)
        self.liveness_status: _ArmatureLivenessStatus = (
            liveness_status
            if isinstance(liveness_status, _ArmatureLivenessStatus)
            else _ArmatureLivenessStatus(liveness_status)
        )
        self.in_live_blender_collection: bool = bool(in_live_blender_collection)
        self.isolation_state: _ArmatureIsolationState = (
            isolation_state
            if isinstance(isolation_state, _ArmatureIsolationState)
            else _ArmatureIsolationState(isolation_state)
        )
        self.tombstone_record: Optional[Dict[str, Any]] = tombstone_record
        self.original_data_ref: Optional[Any] = original_data_ref
        self.registered_name_snapshot: str = str(registered_name_snapshot)
        self.lifecycle_stage: str = str(lifecycle_stage)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "registry_session_id": self.registry_session_id,
            "original_blender_ref": self.original_blender_ref,
            "registration_pointer": self.registration_pointer,
            "original_data_pointer": self.original_data_pointer,
            "liveness_status": (
                self.liveness_status.value
                if isinstance(self.liveness_status, Enum)
                else str(self.liveness_status)
            ),
            "in_live_blender_collection": self.in_live_blender_collection,
            "isolation_state": (
                self.isolation_state.value
                if isinstance(self.isolation_state, Enum)
                else str(self.isolation_state)
            ),
            "tombstone_record": self.tombstone_record,
            "original_data_ref": self.original_data_ref,
            "registered_name_snapshot": self.registered_name_snapshot,
            "lifecycle_stage": self.lifecycle_stage,
        }

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self) -> Tuple[str, ...]:
        return (
            "registry_session_id",
            "original_blender_ref",
            "registration_pointer",
            "original_data_pointer",
            "liveness_status",
            "in_live_blender_collection",
            "isolation_state",
            "tombstone_record",
            "original_data_ref",
            "registered_name_snapshot",
            "lifecycle_stage",
        )


_MANAGED_ARMATURE_IDENTITIES: Dict[str, ArmatureSessionIdentityRecord] = {}
_ISOLATED_FAILED_ARMATURES: Dict[str, Dict[str, Any]] = {}
_ARCHIVED_FAILED_D_TOMBSTONES: Dict[str, Dict[str, Any]] = {}
_FAILED_A_AUDIT_RECORDS: List[Dict[str, Any]] = []
_DEISOLATION_AUDIT_LOG: List[Dict[str, Any]] = []


def _safe_object_name(obj: Any, fallback: str = "<invalid_or_destroyed_object>") -> str:
    """Safely read a Blender object's name without raising ReferenceError."""
    if obj is None:
        return fallback
    try:
        return str(obj.name)
    except BaseException:
        return fallback


def _safe_object_pointer(obj: Any, fallback: int = 0) -> int:
    """Safely read a Blender object's RNA pointer without raising ReferenceError."""
    if obj is None:
        return fallback
    try:
        return int(obj.as_pointer())
    except BaseException:
        return fallback


def _check_original_object_liveness(record: ArmatureSessionIdentityRecord) -> Dict[str, Any]:
    """Evaluate physical Blender Object existence (Eo) independently from data block identity (Ed)."""
    if record is None:
        return {
            "status": "UNKNOWN",
            "object_exists": None,
            "reason": "ArmatureSessionIdentityRecord is None",
        }
    ref = record.original_blender_ref
    if ref is None:
        return {
            "status": "UNKNOWN",
            "object_exists": None,
            "reason": "original_blender_ref is None",
        }

    ref_dead = False
    ref_ptr: Optional[int] = None
    ref_type: Optional[str] = None
    ref_name: Optional[str] = None
    try:
        ref_ptr = int(ref.as_pointer())
        ref_type = str(ref.type)
        ref_name = str(ref.name)
    except ReferenceError as re_err:
        ref_dead = True
    except BaseException as exc:
        return {
            "status": "UNKNOWN",
            "object_exists": None,
            "reason": f"Controlled reference access failure: original_blender_ref access error ({exc})",
        }

    if not ref_dead:
        if ref_ptr != record.registration_pointer:
            return {
                "status": "UNKNOWN",
                "object_exists": None,
                "reason": f"Pointer mismatch: {ref_ptr} != {record.registration_pointer}",
            }

    in_live_objects = False
    try:
        for live_obj in bpy.data.objects.values():
            try:
                if not ref_dead and live_obj.as_pointer() == ref_ptr and live_obj == ref:
                    in_live_objects = True
                    break
            except ReferenceError:
                continue
    except BaseException as exc:
        return {
            "status": "UNKNOWN",
            "object_exists": None,
            "reason": f"bpy.data.objects enumeration failure ({exc})",
        }

    if in_live_objects:
        return {
            "status": "ALIVE",
            "object_exists": True,
            "pointer": ref_ptr,
            "type": ref_type,
            "name": ref_name,
        }

    if ref_dead:
        return {
            "status": "ABSENT",
            "object_exists": False,
            "reason": "original_blender_ref destroyed (ReferenceError) and absent from live bpy.data.objects",
        }

    return {
        "status": "UNKNOWN",
        "object_exists": None,
        "reason": "original_blender_ref is absent from live bpy.data.objects.values() without ReferenceError proof",
    }


def _verify_armature_session_identity_record(
    record: ArmatureSessionIdentityRecord,
    candidate_arm: Optional[bpy.types.Object] = None,
) -> Dict[str, Any]:
    """Simultaneously verify all 7 Armature session identity conditions (Task 10-B-13 Section 4.2)."""
    if record is None:
        return {
            "is_valid": False,
            "checks": {},
            "reasons": ["ArmatureSessionIdentityRecord is None"],
            "registry_session_id": None,
            "object_exists": None,
            "object_liveness_status": "UNKNOWN",
        }

    reasons: List[str] = []
    identity_uncertain = False
    ref = record.original_blender_ref

    # Independent Object Liveness Evaluation (Eo)
    obj_liveness = _check_original_object_liveness(record)
    object_liveness_status = obj_liveness.get("status", "UNKNOWN")
    object_exists = obj_liveness.get("object_exists")

    if object_liveness_status == "ALIVE":
        record.in_live_blender_collection = True
    elif object_liveness_status == "ABSENT":
        record.in_live_blender_collection = False
        record.liveness_status = _ArmatureLivenessStatus.INVALIDATED_DEAD
        if record.lifecycle_stage not in ("TOMBSTONED_FAILED_D", "ARCHIVED_RETIRED"):
            record.lifecycle_stage = "INVALIDATED_DEAD"
    else:  # UNKNOWN
        identity_uncertain = True
        reasons.append(
            f"OBJECT_LIVENESS_UNKNOWN: original object existence cannot be verified ({obj_liveness.get('reason', 'unverified')})"
        )

    # Condition 1: original_blender_ref has not been invalidated
    c1_not_invalidated = (
        object_liveness_status == "ALIVE"
        and record.liveness_status != _ArmatureLivenessStatus.INVALIDATED_DEAD
        and record.isolation_state not in (
            _ArmatureIsolationState.TOMBSTONED_FAILED_D,
            _ArmatureIsolationState.ARCHIVED_RETIRED,
        )
    )
    if not c1_not_invalidated:
        reasons.append(
            f"Condition 1 failed: record liveness_status={record.liveness_status}, "
            f"isolation_state={record.isolation_state}, object_liveness_status={object_liveness_status}"
        )

    # Condition 2: accessing ref does not raise ReferenceError
    c2_no_ref_error = (object_liveness_status == "ALIVE")
    ref_ptr: Optional[int] = None
    ref_type: Optional[str] = None
    ref_data: Optional[Any] = None
    if object_liveness_status == "ALIVE" and ref is not None:
        try:
            ref_ptr = int(ref.as_pointer())
            ref_type = str(ref.type)
            ref_data = ref.data
        except ReferenceError as re_err:
            c2_no_ref_error = False
            reasons.append(f"Condition 2 failed: original_blender_ref raised ReferenceError ({re_err})")
        except BaseException as exc:
            identity_uncertain = True
            c2_no_ref_error = False
            reasons.append(f"Condition 2 failed: original_blender_ref access error ({exc})")
    else:
        c2_no_ref_error = False
        reasons.append(f"Condition 2 failed: {obj_liveness.get('reason', 'original_blender_ref is not live')}")

    # Condition 3: object is in live bpy.data.objects.values()
    c3_in_live_collection = (object_liveness_status == "ALIVE")
    if not c3_in_live_collection:
        reasons.append(
            f"Condition 3 failed: original_blender_ref is absent or unverified in live bpy.data.objects.values() (status={object_liveness_status})"
        )

    # Condition 4: obj.type == 'ARMATURE'
    c4_is_armature_type = bool(c2_no_ref_error and ref_type == "ARMATURE")
    if not c4_is_armature_type:
        reasons.append(f"Condition 4 failed: object type is {ref_type!r}, expected 'ARMATURE'")

    # Condition 6 (on original_blender_ref): obj.as_pointer() == registration_pointer
    c6_ref_ptr_matches = bool(
        c2_no_ref_error
        and ref_ptr is not None
        and ref_ptr == record.registration_pointer
    )
    if not c6_ref_ptr_matches:
        reasons.append(
            f"Condition 6 failed: original_blender_ref pointer {ref_ptr} != "
            f"registration_pointer {record.registration_pointer}"
        )

    # Condition 7: obj.data is valid and obj.data.as_pointer() == original_data_pointer
    c7_data_valid_and_matches = False
    if c2_no_ref_error and ref_data is not None:
        try:
            live_data_ptr = int(ref_data.as_pointer())
            in_armatures = any(
                a.as_pointer() == live_data_ptr and a == ref_data
                for a in bpy.data.armatures.values()
            )
            orig_data_ok = True
            if record.original_data_ref is not None:
                try:
                    orig_data_ok = (
                        record.original_data_ref.as_pointer() == record.original_data_pointer
                        and ref_data == record.original_data_ref
                    )
                except ReferenceError:
                    orig_data_ok = False
            if in_armatures and orig_data_ok and live_data_ptr == record.original_data_pointer:
                c7_data_valid_and_matches = True
        except ReferenceError:
            c7_data_valid_and_matches = False
        except BaseException:
            identity_uncertain = True
            c7_data_valid_and_matches = False
    if not c7_data_valid_and_matches:
        reasons.append(
            "Condition 7 failed: Armature data block is invalid, removed, or pointer does not match original_data_pointer"
        )

    # Update record liveness: separate physical object death from session identity invalidation
    if object_liveness_status == "ALIVE":
        registered_obj_alive = (
            c1_not_invalidated
            and c2_no_ref_error
            and c3_in_live_collection
            and c4_is_armature_type
            and c6_ref_ptr_matches
            and c7_data_valid_and_matches
        )
        if registered_obj_alive:
            record.liveness_status = _ArmatureLivenessStatus.ALIVE_VERIFIED
            try:
                record.registered_name_snapshot = str(ref.name)
            except BaseException:
                pass
        elif not identity_uncertain:
            record.liveness_status = _ArmatureLivenessStatus.INVALIDATED_DEAD
            if record.lifecycle_stage not in ("TOMBSTONED_FAILED_D", "ARCHIVED_RETIRED"):
                record.lifecycle_stage = "INVALIDATED_DEAD"

    # Condition 5 & Condition 6 on candidate_arm (if provided)
    c5_same_blender_ref = True
    c6_pointer_matches = c6_ref_ptr_matches
    if candidate_arm is not None:
        try:
            cand_ptr = int(candidate_arm.as_pointer())
            c5_same_blender_ref = bool(
                c2_no_ref_error
                and ref is not None
                and candidate_arm == ref
            )
            c6_pointer_matches = bool(
                c6_ref_ptr_matches
                and cand_ptr == record.registration_pointer
            )
        except ReferenceError as cand_re:
            c5_same_blender_ref = False
            c6_pointer_matches = False
            reasons.append(f"Condition 5/6 failed: candidate_arm raised ReferenceError ({cand_re})")
        except BaseException as cand_exc:
            identity_uncertain = True
            c5_same_blender_ref = False
            c6_pointer_matches = False
            reasons.append(f"Condition 5/6 failed: candidate_arm invalid ({cand_exc})")

        if not c5_same_blender_ref:
            reasons.append("Condition 5 failed: candidate_arm != record.original_blender_ref")
        if not c6_pointer_matches:
            reasons.append("Condition 6 failed: candidate_arm.as_pointer() != record.registration_pointer")

    checks = {
        "c1_not_invalidated": c1_not_invalidated,
        "c2_no_reference_error": c2_no_ref_error,
        "c3_in_live_blender_collection": c3_in_live_collection,
        "c4_is_armature_type": c4_is_armature_type,
        "c5_same_blender_ref": c5_same_blender_ref,
        "c6_pointer_matches": c6_pointer_matches,
        "c7_data_valid_and_pointer_matches": c7_data_valid_and_matches,
    }
    is_valid = all(checks.values()) and (object_liveness_status == "ALIVE")
    return {
        "is_valid": is_valid,
        "checks": checks,
        "reasons": reasons,
        "registry_session_id": record.registry_session_id,
        "object_exists": object_exists,
        "object_liveness_status": object_liveness_status,
        "identity_verification_uncertain": identity_uncertain,
    }


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
    _sweep_dead_managed_armature_identities()

    if arm is None:
        raise RuntimeError("Cannot resolve ArmatureSessionIdentityRecord: armature object is None")

    # 1. Check if arm matches an existing live verified record
    for rec in _MANAGED_ARMATURE_IDENTITIES.values():
        if rec.liveness_status == _ArmatureLivenessStatus.ALIVE_VERIFIED and rec.isolation_state not in (
            _ArmatureIsolationState.TOMBSTONED_FAILED_D,
            _ArmatureIsolationState.ARCHIVED_RETIRED,
        ):
            ver = _verify_armature_session_identity_record(rec, candidate_arm=arm)
            if ver["is_valid"]:
                return rec

    # 2. Check if arm is the exact dead object wrapper of an existing invalidated/tombstoned record
    for rec in _MANAGED_ARMATURE_IDENTITIES.values():
        if rec.original_blender_ref is arm:
            return rec

    # 3. Validate that arm is a live ARMATURE object in bpy.data.objects before creating a new identity
    try:
        arm_ptr = int(arm.as_pointer())
        arm_type = str(arm.type)
        arm_data = arm.data
        arm_name = str(arm.name)
    except ReferenceError as re_err:
        raise RuntimeError(
            f"Armature session identity rejected: StructRNA object has been destroyed ({re_err})"
        ) from re_err
    except BaseException as exc:
        raise RuntimeError(
            f"Armature session identity rejected: invalid object ({exc})"
        ) from exc

    in_live_objects = False
    try:
        in_live_objects = any(
            o.as_pointer() == arm_ptr and o == arm
            for o in bpy.data.objects.values()
        )
    except BaseException as exc:
        raise RuntimeError(
            f"Armature session identity rejected: cannot verify presence in bpy.data.objects ({exc})"
        ) from exc
    if not in_live_objects or arm_type != "ARMATURE" or arm_data is None:
        raise RuntimeError(
            f"Armature session identity rejected: object '{arm_name}' is not a live ARMATURE in bpy.data.objects"
        )

    try:
        data_ptr = int(arm_data.as_pointer())
    except BaseException as exc:
        raise RuntimeError(
            f"Armature session identity rejected: armature data block is invalid ({exc})"
        ) from exc

    session_id = str(uuid.uuid4())
    while session_id in _MANAGED_ARMATURE_IDENTITIES:
        session_id = str(uuid.uuid4())

    new_rec = ArmatureSessionIdentityRecord(
        registry_session_id=session_id,
        original_blender_ref=arm,
        registration_pointer=arm_ptr,
        original_data_pointer=data_ptr,
        liveness_status=_ArmatureLivenessStatus.ALIVE_VERIFIED,
        in_live_blender_collection=True,
        isolation_state=_ArmatureIsolationState.NONE,
        tombstone_record=None,
        original_data_ref=arm_data,
        registered_name_snapshot=arm_name,
        lifecycle_stage="REGISTERED_ALIVE",
    )
    _MANAGED_ARMATURE_IDENTITIES[session_id] = new_rec
    return new_rec


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
        session_rec.isolation_state = _ArmatureIsolationState.NONE
        if session_rec.liveness_status == _ArmatureLivenessStatus.ALIVE_VERIFIED:
            session_rec.lifecycle_stage = "NORMAL_TERMINAL"
        audit_rec = {
            "transaction_id": tx.tx_id,
            "registry_session_id": session_rec.registry_session_id,
            "failure_class": f_class.value,
            "isolation_state": _ArmatureIsolationState.NONE.value,
            "primary_exception": f"{type(primary_exception).__name__}: {primary_exception}" if primary_exception else None,
            "evidence_status": "PRE_WRITE_ZERO_MUTATION_VERIFIED",
        }
        _FAILED_A_AUDIT_RECORDS.append(audit_rec)
        return audit_rec

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

    grant_id = f"grant_{uuid.uuid4().hex}"
    grant = {
        "grant_id": grant_id,
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "current_isolation_state": current_iso_state,
        "transition_action": transition_action,
        "evidence_status": evidence_status,
        "consumed": False,
        "created_at": time.time(),
    }
    _COORDINATOR_AUTHORIZATION_GRANTS[grant_id] = grant
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
    grant_id = grant_candidate.get("grant_id")
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

    # Consume the grant immediately (single-use enforcement)
    registered_grant["consumed"] = True
    _COORDINATOR_AUTHORIZATION_GRANTS.pop(grant_id, None)

    if action == "CLEAR_TO_NONE":
        if session_rec.isolation_state == _ArmatureIsolationState.TOMBSTONED_FAILED_D:
            raise RuntimeError("Layer 2 rejected de-isolation: TOMBSTONED_FAILED_D cannot return to active status")
        previous_state = session_rec.isolation_state.value
        session_rec.isolation_state = _ArmatureIsolationState.NONE
        session_rec.lifecycle_stage = "NORMAL_TERMINAL"
        _ISOLATED_FAILED_ARMATURES.pop(session_id, None)
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
    _trigger_fault_injection("set_hand_ik_target_during_depsgraph_update")
    _depsgraph_update()


def _clone_snapshot_property_value(val: Any) -> Any:
    """Safely clone an RNA property value into an immutable/independent snapshot representation."""
    if val is None:
        return None
    if isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, (Vector, Euler, Matrix, Quaternion)):
        return val.copy()
    if hasattr(val, "__len__") and hasattr(val, "__getitem__") and not isinstance(val, (str, bytes, dict)):
        # Convert RNA arrays and sequences into independent immutable tuples of cloned values
        return tuple(_clone_snapshot_property_value(elem) for elem in val)
    if isinstance(val, (bpy.types.Object, bpy.types.ID, bpy.types.bpy_struct)):
        # ID / StructRNA reference: keep reference, do not deepcopy Blender C data
        return val
    return val


def _freeze_fingerprint_property_value(val: Any) -> Any:
    """Clone RNA values to recursively immutable, strict structural evidence."""
    if val is None or isinstance(val, (bool, int, float, str, bytes)):
        return val
    if isinstance(val, Vector):
        return tuple(float(v) for v in val)
    if isinstance(val, Euler):
        return ((float(val.x), float(val.y), float(val.z)), str(val.order))
    if isinstance(val, Quaternion):
        return (float(val.w), float(val.x), float(val.y), float(val.z))
    if isinstance(val, Matrix):
        return tuple(tuple(float(v) for v in row) for row in val)
    if isinstance(val, Color):
        return tuple(float(v) for v in val)
    if isinstance(val, (tuple, list)):
        return tuple(_freeze_fingerprint_property_value(v) for v in val)
    if isinstance(val, (set, frozenset)):
        return frozenset(_freeze_fingerprint_property_value(v) for v in val)
    if isinstance(val, dict):
        return tuple(( _freeze_fingerprint_property_value(k),
                       _freeze_fingerprint_property_value(v)) for k, v in val.items())
    if isinstance(val, (bpy.types.Object, bpy.types.ID, bpy.types.bpy_struct)):
        try:
            ptr = int(val.as_pointer())
            if ptr <= 0:
                raise RuntimeError("RNA identity pointer is non-positive")
            rna = getattr(val, "rna_type", None)
            kind = str(getattr(rna, "identifier", type(val).__name__))
            name = str(getattr(val, "name", ""))
            return ("RNA_IDENTITY", kind, ptr, name)
        except BaseException as exc:
            raise RuntimeError(
                f"FINGERPRINT_RNA_IDENTITY_UNVERIFIED: {type(exc).__name__}: {exc}"
            ) from exc
    if hasattr(val, "__len__") and hasattr(val, "__getitem__"):
        return tuple(_freeze_fingerprint_property_value(v) for v in val)
    raise TypeError(f"FINGERPRINT_UNSUPPORTED_TYPE: {type(val).__name__}")




_REQUIRED_ARM_IK_BONE_NAMES: Tuple[str, ...] = (
    "upper_arm.L",
    "upper_arm.R",
    "forearm.L",
    "forearm.R",
    "hand.L",
    "hand.R",
)


def _has_nan_or_inf(val: Any) -> bool:
    """Detect non-finite values; incomplete scans must fail closed, never return False."""
    if val is None or isinstance(val, (bool, int, str, bytes)):
        return False
    if isinstance(val, float):
        return not math.isfinite(val)
    if isinstance(val, (Vector, Euler, Quaternion, Color)):
        return any(_has_nan_or_inf(float(v)) for v in val)
    if isinstance(val, Matrix):
        return any(_has_nan_or_inf(row) for row in val)
    if isinstance(val, dict):
        return any(_has_nan_or_inf(k) or _has_nan_or_inf(v) for k, v in val.items())
    if isinstance(val, (tuple, list, set, frozenset)):
        return any(_has_nan_or_inf(v) for v in val)
    if hasattr(val, "__iter__"):
        # An iterator exception is evidence failure, NOT proof of finiteness.
        return any(_has_nan_or_inf(v) for v in val)
    raise TypeError(f"NONFINITE_SCAN_UNSUPPORTED_TYPE: {type(val).__name__}")


def _capture_pre_snapshot_structural_fingerprint(arm: bpy.types.Object) -> Dict[str, Any]:
    """Capture a comprehensive read-only unrounded structural and value fingerprint before SNAPSHOTTING."""
    char_col = bpy.data.collections.get("Character")
    scene_children = bpy.context.scene.collection.children if (bpy.context and bpy.context.scene) else []
    char_col_fp = None
    if char_col is not None:
        char_col_fp = {
            "col_ptr": int(char_col.as_pointer()),
            "name": str(char_col.name),
            "children_of_scene": bool(char_col.name in scene_children),
            "parent_ptrs": tuple(sorted(p.as_pointer() for p in bpy.data.collections if any(ch.as_pointer() == char_col.as_pointer() for ch in p.children))),
            "child_ptrs": tuple(sorted(ch.as_pointer() for ch in char_col.children)),
            "object_ptrs": tuple(sorted(o.as_pointer() for o in char_col.objects)),
            "object_names": tuple(sorted(str(o.name) for o in char_col.objects)),
        }

    ctrl_names = (
        ARM_IK_TARGET_NAMES["L"],
        ARM_IK_TARGET_NAMES["R"],
        ARM_POLE_TARGET_NAMES["L"],
        ARM_POLE_TARGET_NAMES["R"],
    )
    ctrls_fp: Dict[str, Any] = {}
    for c_name in ctrl_names:
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is None:
            ctrls_fp[c_name] = None
        else:
            ctrls_fp[c_name] = {
                "obj_ptr": int(c_obj.as_pointer()),
                "data_ptr": int(c_obj.data.as_pointer()) if getattr(c_obj, "data", None) is not None else None,
                "name": str(c_obj.name),
                "type": str(c_obj.type),
                "parent_ptr": int(c_obj.parent.as_pointer()) if c_obj.parent is not None else None,
                "matrix_parent_inverse": tuple(tuple(float(v) for v in row) for row in c_obj.matrix_parent_inverse),
                "location": tuple(float(v) for v in c_obj.location),
                "rotation_mode": str(c_obj.rotation_mode),
                "rotation_euler": tuple(float(v) for v in c_obj.rotation_euler),
                "rotation_quaternion": tuple(float(v) for v in c_obj.rotation_quaternion),
                "rotation_axis_angle": tuple(float(v) for v in c_obj.rotation_axis_angle),
                "scale": tuple(float(v) for v in c_obj.scale),
                "matrix_world": tuple(tuple(float(v) for v in row) for row in c_obj.matrix_world),
                "empty_display_type": getattr(c_obj, "empty_display_type", None) if c_obj.type == "EMPTY" else None,
                "empty_display_size": float(getattr(c_obj, "empty_display_size", 0.0)) if (c_obj.type == "EMPTY" and getattr(c_obj, "empty_display_size", None) is not None) else None,
                "users_collection_ptrs": tuple(sorted(c.as_pointer() for c in c_obj.users_collection)),
                "users_collection_names": tuple(sorted(str(c.name) for c in c_obj.users_collection)),
            }

    bones_fp: Dict[str, Any] = {}
    present_arm_bones: List[str] = []
    for b_name in _REQUIRED_ARM_IK_BONE_NAMES:
        pbone = arm.pose.bones.get(b_name) if getattr(arm, "pose", None) else None
        if pbone is None:
            bones_fp[b_name] = None
            continue
        present_arm_bones.append(b_name)
        con_list: List[Dict[str, Any]] = []
        for con in pbone.constraints:
            c_dict: Dict[str, Any] = {
                "con_ptr": int(con.as_pointer()),
                "name": str(con.name),
                "type": str(con.type),
                "influence": float(con.influence),
                "mute": bool(con.mute),
                "target_ptr": int(con.target.as_pointer()) if getattr(con, "target", None) is not None else None,
                "subtarget": str(getattr(con, "subtarget", "")),
                "pole_target_ptr": int(con.pole_target.as_pointer()) if getattr(con, "pole_target", None) is not None else None,
                "pole_subtarget": str(getattr(con, "pole_subtarget", "")),
            }
            if con.type == "IK":
                c_dict.update({
                    "chain_count": int(getattr(con, "chain_count", 0)),
                    "use_tail": bool(getattr(con, "use_tail", True)),
                    "use_stretch": bool(getattr(con, "use_stretch", False)),
                    "pole_angle": float(getattr(con, "pole_angle", 0.0)),
                    "iterations": int(getattr(con, "iterations", 500)),
                })
            elif con.type == "COPY_ROTATION":
                c_dict.update({
                    "target_space": str(getattr(con, "target_space", "WORLD")),
                    "owner_space": str(getattr(con, "owner_space", "WORLD")),
                    "mix_mode": str(getattr(con, "mix_mode", "REPLACE")),
                    "use_x": bool(getattr(con, "use_x", True)),
                    "use_y": bool(getattr(con, "use_y", True)),
                    "use_z": bool(getattr(con, "use_z", True)),
                    "invert_x": bool(getattr(con, "invert_x", False)),
                    "invert_y": bool(getattr(con, "invert_y", False)),
                    "invert_z": bool(getattr(con, "invert_z", False)),
                    "use_offset": bool(getattr(con, "use_offset", False)),
                })

            generic_props: Dict[str, Any] = {}
            for p in con.rna_type.properties:
                if not p.is_readonly and p.identifier not in ("rna_type", "name", "mute", "influence"):
                    try:
                        val = getattr(con, p.identifier)
                        cloned = _clone_snapshot_property_value(val)
                        generic_props[p.identifier] = _freeze_fingerprint_property_value(cloned)
                    except BaseException as exc:
                        raise RuntimeError(
                            "FINGERPRINT_PROPERTY_CAPTURE_FAILED: "
                            f"bone={pbone.name}, "
                            f"constraint={con.name}, "
                            f"type={con.type}, "
                            f"property={p.identifier}, "
                            f"cause={type(exc).__name__}: {exc}"
                        ) from exc
            c_dict["generic_props"] = generic_props
            con_list.append(c_dict)

        bones_fp[b_name] = {
            "location": tuple(float(v) for v in pbone.location),
            "rotation_mode": str(pbone.rotation_mode),
            "rotation_euler": tuple(float(v) for v in pbone.rotation_euler),
            "rotation_quaternion": tuple(float(v) for v in pbone.rotation_quaternion),
            "rotation_axis_angle": tuple(float(v) for v in pbone.rotation_axis_angle),
            "scale": tuple(float(v) for v in pbone.scale),
            "matrix_basis": tuple(tuple(float(v) for v in row) for row in pbone.matrix_basis),
            "lock_ik_x": bool(pbone.lock_ik_x),
            "lock_ik_y": bool(pbone.lock_ik_y),
            "lock_ik_z": bool(pbone.lock_ik_z),
            "use_ik_limit_x": bool(pbone.use_ik_limit_x),
            "use_ik_limit_y": bool(pbone.use_ik_limit_y),
            "use_ik_limit_z": bool(pbone.use_ik_limit_z),
            "ik_min_x": float(pbone.ik_min_x),
            "ik_max_x": float(pbone.ik_max_x),
            "ik_min_y": float(pbone.ik_min_y),
            "ik_max_y": float(pbone.ik_max_y),
            "ik_min_z": float(pbone.ik_min_z),
            "ik_max_z": float(pbone.ik_max_z),
            "constraints": tuple(con_list),
        }

    return {
        "arm_ptr": int(arm.as_pointer()),
        "arm_name": str(arm.name),
        "data_ptr": int(arm.data.as_pointer()) if getattr(arm, "data", None) is not None else None,
        "total_pose_bone_count": len(arm.pose.bones) if getattr(arm, "pose", None) else 0,
        "present_arm_bones": tuple(present_arm_bones),
        "character_collection": char_col_fp,
        "controllers": ctrls_fp,
        "pose_bones": bones_fp,
        "all_object_ptrs": frozenset(int(o.as_pointer()) for o in bpy.data.objects),
        "all_collection_ptrs": frozenset(int(c.as_pointer()) for c in bpy.data.collections),
    }


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
    _trigger_fault_injection(
        "during_snapshot_creation",
        {
            "arm": arm,
            "tx": (_ACTIVE_TRANSACTION_STACK[-1] if _ACTIVE_TRANSACTION_STACK else None),
        },
    )
    _depsgraph_update()

    # 1. Collections snapshot
    char_col = bpy.data.collections.get("Character")
    scene_children = bpy.context.scene.collection.children if bpy.context.scene else []
    char_col_data = {
        "existed": char_col is not None,
        "col_ref": char_col,
        "col_ptr": char_col.as_pointer() if (char_col is not None and hasattr(char_col, "as_pointer")) else None,
        "name": char_col.name if char_col is not None else None,
        "children_of_scene": (char_col is not None and char_col.name in scene_children),
        "parent_collections": [c.name for c in bpy.data.collections if char_col is not None and char_col.name in c.children],
        "child_collections": [c.name for c in char_col.children] if char_col is not None else [],
        "object_names": set(char_col.objects.keys()) if char_col is not None else set(),
        "parent_refs": [
            parent
            for parent in bpy.data.collections
            if char_col is not None
            and any(child.as_pointer() == char_col.as_pointer() for child in parent.children)
        ],
        "child_refs": (
            list(char_col.children)
            if char_col is not None
            else []
        ),
        "object_refs": (
            list(char_col.objects)
            if char_col is not None
            else []
        ),
    }

    # 2. Controllers snapshot (HandIK.L/R, ElbowPole.L/R)
    ctrl_names = (
        ARM_IK_TARGET_NAMES["L"],
        ARM_IK_TARGET_NAMES["R"],
        ARM_POLE_TARGET_NAMES["L"],
        ARM_POLE_TARGET_NAMES["R"],
    )
    controllers_data: Dict[str, Dict[str, Any]] = {}
    for c_name in ctrl_names:
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is None:
            controllers_data[c_name] = {"exists": False}
        else:
            controllers_data[c_name] = {
                "exists": True,
                "obj_ref": c_obj,
                "obj_ptr": c_obj.as_pointer() if hasattr(c_obj, "as_pointer") else None,
                "data_ref": getattr(c_obj, "data", None),
                "data_ptr": c_obj.data.as_pointer() if getattr(c_obj, "data", None) and hasattr(c_obj.data, "as_pointer") else None,
                "obj_name": c_obj.name,
                "type": c_obj.type,
                "parent": c_obj.parent,
                "matrix_parent_inverse": c_obj.matrix_parent_inverse.copy(),
                "location": c_obj.location.copy(),
                "rotation_mode": c_obj.rotation_mode,
                "rotation_euler": c_obj.rotation_euler.copy(),
                "rotation_quaternion": c_obj.rotation_quaternion.copy(),
                "rotation_axis_angle": tuple(c_obj.rotation_axis_angle),
                "scale": c_obj.scale.copy(),
                "matrix_world": c_obj.matrix_world.copy(),
                "empty_display_type": getattr(c_obj, "empty_display_type", None) if c_obj.type == "EMPTY" else None,
                "empty_display_size": getattr(c_obj, "empty_display_size", None) if c_obj.type == "EMPTY" else None,
                "collections": [c.name for c in c_obj.users_collection],
                "collection_refs": list(c_obj.users_collection),
                "collection_ptrs": [
                    c.as_pointer()
                    for c in c_obj.users_collection
                    if hasattr(c, "as_pointer")
                ],
            }

    # 3. Pose bones snapshot (upper_arm, forearm, hand across L and R)
    bone_names = (
        "upper_arm.L", "upper_arm.R",
        "forearm.L", "forearm.R",
        "hand.L", "hand.R",
    )
    pose_bones_data: Dict[str, Dict[str, Any]] = {}
    for b_name in bone_names:
        pbone = arm.pose.bones.get(b_name)
        if pbone is None:
            continue

        con_list: List[Dict[str, Any]] = []
        for con in pbone.constraints:
            c_dict: Dict[str, Any] = {
                "name": con.name,
                "type": con.type,
                "con_ref": con,
                "con_ptr": con.as_pointer() if hasattr(con, "as_pointer") else None,
                "influence": float(con.influence),
                "mute": bool(con.mute),
                "target": getattr(con, "target", None),
                "subtarget": getattr(con, "subtarget", ""),
                "pole_target": getattr(con, "pole_target", None),
                "pole_subtarget": getattr(con, "pole_subtarget", ""),
            }
            if con.type == "IK":
                c_dict.update({
                    "chain_count": getattr(con, "chain_count", 0),
                    "use_tail": getattr(con, "use_tail", True),
                    "use_stretch": getattr(con, "use_stretch", False),
                    "pole_angle": float(getattr(con, "pole_angle", 0.0)),
                    "iterations": getattr(con, "iterations", 500),
                })
            elif con.type == "COPY_ROTATION":
                c_dict.update({
                    "target_space": getattr(con, "target_space", "WORLD"),
                    "owner_space": getattr(con, "owner_space", "WORLD"),
                    "mix_mode": getattr(con, "mix_mode", "REPLACE"),
                    "use_x": getattr(con, "use_x", True),
                    "use_y": getattr(con, "use_y", True),
                    "use_z": getattr(con, "use_z", True),
                    "invert_x": getattr(con, "invert_x", False),
                    "invert_y": getattr(con, "invert_y", False),
                    "invert_z": getattr(con, "invert_z", False),
                    "use_offset": getattr(con, "use_offset", False),
                })

            generic_props: Dict[str, Any] = {}
            for p in con.rna_type.properties:
                if not p.is_readonly and p.identifier not in ("rna_type", "name", "mute", "influence"):
                    try:
                        val = getattr(con, p.identifier)
                    except Exception as pe:
                        raise RuntimeError(
                            f"Snapshot failed: cannot read property '{p.identifier}' (type {p.type}) "
                            f"on constraint '{con.name}' ({con.type}) on bone '{pbone.name}': {pe}"
                        ) from pe
                    generic_props[p.identifier] = _clone_snapshot_property_value(val)

            c_dict["generic_props"] = generic_props
            con_list.append(c_dict)

        pose_bones_data[b_name] = {
            "name": b_name,
            "location": pbone.location.copy(),
            "rotation_mode": pbone.rotation_mode,
            "rotation_euler": pbone.rotation_euler.copy(),
            "rotation_quaternion": pbone.rotation_quaternion.copy(),
            "rotation_axis_angle": tuple(pbone.rotation_axis_angle),
            "scale": pbone.scale.copy(),
            "matrix_basis": pbone.matrix_basis.copy(),
            "lock_ik_x": bool(pbone.lock_ik_x),
            "lock_ik_y": bool(pbone.lock_ik_y),
            "lock_ik_z": bool(pbone.lock_ik_z),
            "use_ik_limit_x": bool(pbone.use_ik_limit_x),
            "use_ik_limit_y": bool(pbone.use_ik_limit_y),
            "use_ik_limit_z": bool(pbone.use_ik_limit_z),
            "ik_min_x": float(pbone.ik_min_x),
            "ik_max_x": float(pbone.ik_max_x),
            "ik_min_y": float(pbone.ik_min_y),
            "ik_max_y": float(pbone.ik_max_y),
            "ik_min_z": float(pbone.ik_min_z),
            "ik_max_z": float(pbone.ik_max_z),
            "constraints": con_list,
        }

    return {
        "character_collection": char_col_data,
        "controllers": controllers_data,
        "pose_bones": pose_bones_data,
    }


def _find_live_object_by_identity(
    obj_ref: bpy.types.Object,
    expected_ptr: int,
) -> Optional[bpy.types.Object]:
    """Resolve the original live Blender object.

    A matching name alone never proves identity.
    """
    try:
        ref_ptr = obj_ref.as_pointer()
    except ReferenceError:
        return None

    if ref_ptr != expected_ptr:
        return None

    for candidate in bpy.data.objects:
        if candidate.as_pointer() != expected_ptr:
            continue

        try:
            if candidate == obj_ref:
                return candidate
        except ReferenceError:
            return None

    return None


def _find_live_collection_by_identity(
    col_ref: Optional[bpy.types.Collection],
    expected_ptr: Optional[int],
) -> Optional[bpy.types.Collection]:
    """Resolve the original live Blender Collection (user or scene master collection) by identity.

    A matching name alone never proves identity.
    """
    if col_ref is None and expected_ptr is None:
        return None

    if col_ref is not None:
        try:
            ref_ptr = col_ref.as_pointer()
        except ReferenceError:
            return None
        if expected_ptr is not None and ref_ptr != expected_ptr:
            return None
        target_ptr = expected_ptr if expected_ptr is not None else ref_ptr
    else:
        target_ptr = expected_ptr

    for candidate in bpy.data.collections:
        try:
            if candidate.as_pointer() != target_ptr:
                continue
            if col_ref is None or candidate == col_ref:
                return candidate
        except ReferenceError:
            continue

    if bpy.context and getattr(bpy.context, "scene", None) and getattr(bpy.context.scene, "collection", None):
        sc = bpy.context.scene.collection
        try:
            if sc.as_pointer() == target_ptr and (col_ref is None or sc == col_ref):
                return sc
        except ReferenceError:
            pass

    for scene in bpy.data.scenes:
        sc = getattr(scene, "collection", None)
        if sc is None:
            continue
        try:
            if sc.as_pointer() == target_ptr and (col_ref is None or sc == col_ref):
                return sc
        except ReferenceError:
            continue

    return None


def _is_object_linked_to_collection_by_identity(
    collection: bpy.types.Collection,
    obj_ref: Optional[bpy.types.Object],
    expected_obj_ptr: Optional[int],
) -> bool:
    """Check whether an object is currently linked to a collection by reference and pointer identity."""
    if collection is None:
        return False
    if obj_ref is None and expected_obj_ptr is None:
        return False

    if obj_ref is not None:
        try:
            ref_ptr = obj_ref.as_pointer()
        except ReferenceError:
            return False
        if expected_obj_ptr is not None and ref_ptr != expected_obj_ptr:
            return False
        target_ptr = expected_obj_ptr if expected_obj_ptr is not None else ref_ptr
    else:
        target_ptr = expected_obj_ptr

    try:
        for candidate in collection.objects:
            try:
                if candidate.as_pointer() != target_ptr:
                    continue
                if obj_ref is None or candidate == obj_ref:
                    return True
            except ReferenceError:
                continue
    except ReferenceError:
        return False

    return False


def _authorized_link_object_to_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object link executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    global _ACTIVE_TRANSACTION_STACK
    if active_tx is None and _ACTIVE_TRANSACTION_STACK:
        active_tx = _ACTIVE_TRANSACTION_STACK[-1]

    if active_tx is None:
        obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
        if not _is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
            collection.objects.link(obj)
        return None

    col_ptr = collection.as_pointer() if hasattr(collection, "as_pointer") else None
    obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
    obj_name = getattr(obj, "name", "<unknown>")

    # 1. PREPARE: Register relationship mutation before executing any Blender C-API write
    already_linked = _is_object_linked_to_collection_by_identity(collection, obj, obj_ptr)
    category = "PRE_EXISTING_ORIGINAL" if already_linked else "TX_ADDED"
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=collection,
        target_reference=obj,
        original_relationship_state={
            "linked": already_linked,
            "category": category,
            "col_ptr": col_ptr,
            "obj_ptr": obj_ptr,
        },
        intended_mutation="COLLECTION_OBJECT_LINK",
    )

    _trigger_fault_injection(
        "relationship_link_after_prepare",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )

    # Duplicate link on pre-existing relationship: transition PREPARED -> NO_EFFECT with zero revocation rights
    if already_linked:
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.NO_EFFECT,
        )
        return op_record

    # 2. APPLY: Transition PREPARED -> APPLYING and execute C-API link with exception-window inspection
    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.APPLYING,
    )
    try:
        _trigger_fault_injection(
            "relationship_link_during_apply_before_c_api",
            {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
        )
        live_col = _find_live_collection_by_identity(collection, col_ptr)
        live_obj = _find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if live_col is None or live_obj is None:
            raise RuntimeError("Target object or collection identity invalid during link apply")

        live_col.objects.link(live_obj)

        _trigger_fault_injection(
            "relationship_link_during_apply_after_c_api",
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
        elif _is_object_linked_to_collection_by_identity(check_col, check_obj, obj_ptr):
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.APPLIED_VERIFIED,
            )
            active_tx.register_created_collection_link(check_col, check_obj)
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.NO_EFFECT,
            )
        raise

    if not _is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection link apply did not take effect in RNA for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.APPLIED_VERIFIED,
    )
    active_tx.register_created_collection_link(collection, obj)

    # 3. CONFIRM: Verify live RNA state and transition APPLIED_VERIFIED -> CONFIRMED
    _trigger_fault_injection(
        "relationship_link_before_confirm",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )
    confirm_col = _find_live_collection_by_identity(collection, col_ptr)
    confirm_obj = _find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
    if (
        confirm_col is None
        or confirm_obj is None
        or not _is_object_linked_to_collection_by_identity(confirm_col, confirm_obj, obj_ptr)
    ):
        active_tx.update_relationship_mutation_state(
            op_record,
            _RelationshipOperationState.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection link verification failed at CONFIRM stage for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        _RelationshipOperationState.CONFIRMED,
    )
    return op_record


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
        return

    try:
        _trigger_fault_injection(
            "during_relationship_rollback_undo",
            {"op": op_record, "tx": active_tx},
        )
    except BaseException:
        if op_record.get("operation_state") in (
            _RelationshipOperationState.APPLYING,
            _RelationshipOperationState.APPLIED_VERIFIED,
            _RelationshipOperationState.CONFIRMED,
        ):
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
        return

    src_id = op_record.get("source_identity", {})
    tgt_id = op_record.get("target_identity", {})
    orig_rel = op_record.get("original_relationship_state", {})
    category = orig_rel.get("category", "OWNERSHIP_UNKNOWN")
    mutation = op_record.get("intended_mutation")

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
        return

    if mutation == "COLLECTION_OBJECT_LINK":
        if category != "TX_ADDED":
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            return
        try:
            if _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                live_col.objects.unlink(live_obj)
            still_linked = _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        except BaseException:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            return

        if still_linked:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
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
            return
        try:
            if not _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                live_col.objects.link(live_obj)
            now_linked = _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        except BaseException:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
            return

        if not now_linked:
            active_tx.update_relationship_mutation_state(
                op_record,
                _RelationshipOperationState.RECOVERY_UNCERTAIN,
            )
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
        live_col.objects.link(live_obj)


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

        # Backward-compatibility for any manually registered created_collection_links not in prepared_relationship_mutations
        for link_rec in reversed(list(getattr(active_tx, "created_collection_links", []))):
            col_ref = link_rec.get("col_ref")
            col_ptr = link_rec.get("col_ptr")
            obj_ref = link_rec.get("obj_ref")
            obj_ptr = link_rec.get("obj_ptr")
            if (col_ptr, obj_ptr) in logged_link_pairs:
                continue
            live_col = _find_live_collection_by_identity(col_ref, col_ptr)
            live_obj = _find_live_object_by_identity(obj_ref, obj_ptr) if obj_ptr is not None else None
            if live_col is not None and live_obj is not None:
                if _is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                    live_col.objects.unlink(live_obj)

    if phase in ("ALL", "POST_CONTROLLER_RESTORE"):
        if active_tx is not None:
            for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
                if op_record.get("intended_mutation") != "COLLECTION_OBJECT_LINK" or phase == "ALL":
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
                for col_name in c_snap.get("collections", []):
                    col = _find_collection_by_name(col_name)
                    if col is not None:
                        _authorized_ensure_snapshot_collection_link(
                            col, live_original, original_ptr, restoration_errors
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
                    for col_name in stashed.get("collections", []):
                        col = _find_collection_by_name(col_name)
                        if col is not None:
                            _authorized_ensure_snapshot_collection_link(
                                col, live_stashed, obj_ptr, restoration_errors
                            )


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

    # Step 1: Controller cleanup, stashed object restoration, and transform restoration
    # 1.0a: Revert transaction-created Collection <-> Object links via Layer 3 before removing created controllers
    _authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase="PRE_CONTROLLER_REMOVE",
    )

    # 1.0b: Clean up transaction-owned controller objects by identity
    if active_tx is not None:
        for record in getattr(active_tx, "created_controller_objects", []):
            live_obj = _find_live_object_by_identity(
                record["obj_ref"],
                record["obj_ptr"],
            )

            if live_obj is None:
                # Never delete a replacement by name.
                continue

            bpy.data.objects.remove(
                live_obj,
                do_unlink=True,
            )

            remaining = _find_live_object_by_identity(
                record["obj_ref"],
                record["obj_ptr"],
            )

            if remaining is not None:
                restoration_errors.append(
                    "Transaction-owned controller removal failed"
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

        live_original.parent = c_snap["parent"]
        live_original.matrix_parent_inverse = c_snap["matrix_parent_inverse"].copy()
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
    pose_bones_snap = snapshot.get("pose_bones", {})

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

        # 2.1: Remove ONLY constraints explicitly registered as created by this transaction
        if active_tx is not None:
            for reg_con in list(getattr(active_tx, "created_constraints", [])):
                if reg_con.get("bone_name") == b_name or reg_con.get("pbone") == pbone:
                    expected_ptr = reg_con.get("con_ptr")
                    con_ref = reg_con.get("con_ref")
                    target = None
                    for candidate in list(pbone.constraints):
                        try:
                            if expected_ptr and candidate.as_pointer() == expected_ptr:
                                target = candidate
                                break
                            elif con_ref is not None and candidate == con_ref:
                                target = candidate
                                break
                        except ReferenceError:
                            continue
                    if target is not None:
                        pbone.constraints.remove(target)
                        still_present = any(
                            (expected_ptr and c.as_pointer() == expected_ptr)
                            for c in pbone.constraints
                        )
                        if still_present:
                            restoration_errors.append(
                                f"Failed to remove transaction-created constraint: {reg_con.get('created_name')}"
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

            if hasattr(con, "target"):
                con.target = sc.get("target")
            if hasattr(con, "subtarget"):
                con.subtarget = sc.get("subtarget", "")
            if hasattr(con, "pole_target"):
                con.pole_target = sc.get("pole_target")
            if hasattr(con, "pole_subtarget"):
                con.pole_subtarget = sc.get("pole_subtarget", "")

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

    # Step 3: Collection hierarchy restoration with strict ownership isolation
    # Only delete collections explicitly registered as created by this transaction!
    if active_tx is not None:
        for reg in list(getattr(active_tx, "created_collections", [])):
            col_ref = reg.get("col_ref")
            col_ptr = reg.get("col_ptr")
            created_name = reg.get("created_name")

            target_col = None
            if col_ref is not None:
                try:
                    if col_ref.name in bpy.data.collections and bpy.data.collections[col_ref.name] == col_ref:
                        target_col = col_ref
                except ReferenceError:
                    target_col = None
            if target_col is None and created_name in bpy.data.collections:
                c_candidate = bpy.data.collections[created_name]
                if col_ptr is None or c_candidate.as_pointer() == col_ptr:
                    target_col = c_candidate

            if target_col is not None:
                for p_col in list(bpy.data.collections):
                    if target_col.name in p_col.children:
                        p_col.children.unlink(target_col)
                for scene in list(bpy.data.scenes):
                    if target_col.name in scene.collection.children:
                        scene.collection.children.unlink(target_col)
                bpy.data.collections.remove(target_col)

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
                if live_ptr != original_ptr:
                    restoration_errors.append(
                        "Character collection identity changed"
                    )
                else:
                    # Identity verified! Restore name, parents, children, and members.
                    if orig_name is not None and col.name != orig_name:
                        col.name = orig_name

                    should_be_in_scene = char_col_snap.get("children_of_scene", False)
                    is_in_scene = any(
                        c.as_pointer() == col.as_pointer()
                        for c in (bpy.context.scene.collection.children if bpy.context.scene else [])
                    )
                    if should_be_in_scene and not is_in_scene:
                        bpy.context.scene.collection.children.link(col)

                    # Parent Collection restoration by reference
                    expected_parents = char_col_snap.get(
                        "parent_refs", []
                    )
                    for parent in expected_parents:
                        try:
                            parent_ptr = parent.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Original Character parent collection destroyed"
                            )
                            continue

                        linked = any(
                            child.as_pointer() == col.as_pointer()
                            for child in parent.children
                        )
                        if not linked:
                            parent.children.link(col)

                    # Child Collection restoration by reference
                    expected_children = char_col_snap.get(
                        "child_refs", []
                    )
                    for child in expected_children:
                        try:
                            child_ptr = child.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Original Character child collection destroyed"
                            )
                            continue

                        linked = any(
                            current.as_pointer() == child_ptr
                            for current in col.children
                        )
                        if not linked:
                            col.children.link(child)

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


class _ArmRigTransactionContext:
    """Active transaction execution state tracking."""

    def __init__(
        self,
        arm: bpy.types.Object,
        session_record: Optional[ArmatureSessionIdentityRecord] = None,
    ):
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
        self.created_constraints: List[
            Dict[str, Any]
        ] = []
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
        src_ptr = source_reference.as_pointer() if hasattr(source_reference, "as_pointer") else None
        tgt_ptr = target_reference.as_pointer() if hasattr(target_reference, "as_pointer") else None
        src_name = getattr(source_reference, "name", None)
        tgt_name = getattr(target_reference, "name", None)

        op_record: Dict[str, Any] = {
            "operation_id": f"rel_{self.tx_id}_{len(self.prepared_relationship_mutations) + 1:04d}_{uuid.uuid4().hex[:6]}",
            "transaction_id": self.tx_id,
            "source_reference": source_reference,
            "target_reference": target_reference,
            "source_identity": {
                "ref": source_reference,
                "ptr": src_ptr,
                "name": src_name,
                "kind": type(source_reference).__name__,
            },
            "target_identity": {
                "ref": target_reference,
                "ptr": tgt_ptr,
                "name": tgt_name,
                "kind": type(target_reference).__name__,
            },
            "original_relationship_state": dict(original_relationship_state),
            "intended_mutation": intended_mutation,
            "operation_state": _RelationshipOperationState.PREPARED,
        }
        self.prepared_relationship_mutations.append(op_record)
        return op_record

    def update_relationship_mutation_state(
        self,
        op_record: Dict[str, Any],
        new_state: _RelationshipOperationState,
    ) -> None:
        """Transition a relationship operation record across the approved 7-state machine."""
        raw_current = op_record.get("operation_state")
        current_state = (
            raw_current
            if isinstance(raw_current, _RelationshipOperationState)
            else _RelationshipOperationState(raw_current)
        )
        target_state = (
            new_state
            if isinstance(new_state, _RelationshipOperationState)
            else _RelationshipOperationState(new_state)
        )
        if (current_state, target_state) not in _LEGAL_RELATIONSHIP_LOG_TRANSITIONS:
            raise RuntimeError(
                f"Illegal relationship operation state transition: {current_state} -> {target_state}"
            )
        op_record["operation_state"] = target_state

    def register_created_controller(
        self,
        obj: bpy.types.Object,
    ) -> None:
        """Register a controller created by this transaction."""
        obj_ptr = obj.as_pointer()

        for record in self.created_controller_objects:
            if record["obj_ptr"] == obj_ptr:
                raise RuntimeError(
                    "Duplicate transaction controller registration"
                )

        self.created_controller_objects.append({
            "obj_ref": obj,
            "obj_ptr": obj_ptr,
            "created_name": obj.name,
        })

    def register_created_constraint(
        self,
        pbone: bpy.types.PoseBone,
        con: bpy.types.Constraint,
    ) -> None:
        """Register a constraint created by this transaction for identity-based ownership."""
        con_ptr = con.as_pointer()

        for record in self.created_constraints:
            if record["con_ptr"] == con_ptr:
                raise RuntimeError(
                    "Duplicate transaction constraint registration"
                )

        self.created_constraints.append({
            "pbone": pbone,
            "con_ref": con,
            "con_ptr": con_ptr,
            "created_name": con.name,
            "bone_name": pbone.name,
        })

    def register_created_collection_link(
        self,
        col: bpy.types.Collection,
        obj: bpy.types.Object,
    ) -> None:
        """Register an object-to-collection link mutation created by this transaction."""
        col_ptr = col.as_pointer() if hasattr(col, "as_pointer") else None
        obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None

        for record in self.created_collection_links:
            if record["col_ptr"] == col_ptr and record["obj_ptr"] == obj_ptr:
                return

        self.created_collection_links.append({
            "col_ref": col,
            "col_ptr": col_ptr,
            "col_name": col.name,
            "obj_ref": obj,
            "obj_ptr": obj_ptr,
            "obj_name": obj.name,
        })

    def register_created_collection(
        self,
        col: bpy.types.Collection,
        initial_parent: Optional[bpy.types.Collection] = None,
    ) -> None:
        """Register a collection created within this transaction for ownership tracking."""
        rec = {
            "col_ref": col,
            "col_ptr": col.as_pointer() if hasattr(col, "as_pointer") else None,
            "created_name": col.name,
            "initial_parent": initial_parent,
        }
        self.created_collections.append(rec)

    def retry_cleanup(self) -> None:
        """Idempotently retry irreversible cleanup of pending stashed resources."""
        if self.state == _ArmRigTransactionState.FAILED:
            raise RuntimeError(
                f"Cannot execute retry_cleanup on FAILED transaction {self.tx_id}: "
                "FAILED -> COMMITTED transition is strictly forbidden"
            )
        cleanup_failures: List[str] = []

        # ------------------------------------------------------
        # Task 10-B-8
        # Identity-safe cleanup of stashed constraints
        # ------------------------------------------------------

        for stashed_con in list(
            self.uncleaned_stashed_constraints
        ):
            try:
                pbone = stashed_con["pbone"]

                original_ref = stashed_con.get("con")
                expected_ptr = stashed_con.get("con_ptr")

                if expected_ptr is None and original_ref is None:
                    raise RuntimeError(
                        "Stashed constraint identity record incomplete"
                    )

                if original_ref is not None:
                    try:
                        live_ptr = original_ref.as_pointer()
                    except ReferenceError:
                        raise RuntimeError(
                            "Stashed constraint original reference invalid"
                        )

                    if expected_ptr is not None and live_ptr != expected_ptr:
                        raise RuntimeError(
                            "Stashed constraint identity changed"
                        )

                    matches = [
                        candidate
                        for candidate in pbone.constraints
                        if (
                            (expected_ptr is None or candidate.as_pointer() == expected_ptr)
                            and candidate == original_ref
                        )
                    ]
                else:
                    matches = [
                        candidate
                        for candidate in pbone.constraints
                        if candidate.as_pointer() == expected_ptr
                    ]

                if len(matches) > 1:
                    raise RuntimeError(
                        "Multiple live constraints match "
                        "the same recorded identity"
                    )

                if len(matches) == 1:
                    target = matches[0]

                    pbone.constraints.remove(target)

                    still_present = any(
                        candidate.as_pointer() == expected_ptr
                        for candidate in pbone.constraints
                    )

                    if still_present:
                        raise RuntimeError(
                            "Stashed constraint removal did not "
                            "remove the recorded identity"
                        )

                # No live match means the recorded resource
                # is already absent. Never remove by name.

                self.uncleaned_stashed_constraints.remove(
                    stashed_con
                )

            except Exception as exc:
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
                                    stashed_orig_name = stashed.get("original_name")
                                    if stashed_orig_name is not None or not getattr(self, "created_datablocks", None):
                                        raise RuntimeError(
                                            f"DataBlock {data_name} claims TYPE_A_TX_CREATED but lacks credible transaction creation provenance"
                                        )
                                elif provenance == "TYPE_B_PRE_EXISTING_EXPLICIT_GRANT":
                                    auth_src = matching_auth.get("authorization_source")
                                    if not auth_src or auth_src in ("UNKNOWN", "NONE", "UNPROVEN"):
                                        raise RuntimeError(
                                            f"DataBlock {data_name} with TYPE_B provenance lacks valid explicit authorization_source: {auth_src}"
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

                                # All 12 conditions verified: delete without do_unlink=True
                                target_coll.remove(target_data, do_unlink=False)

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
                    cleanup_failures.append(f"Failed to clean up datablock for {stashed.get('original_name')}: {de}")

            # Only remove record from uncleaned_stashed_objects when BOTH object and datablock are cleaned
            if stashed.get("obj_cleaned", False) and stashed.get("data_cleaned", False):
                if stashed in self.uncleaned_stashed_objects:
                    self.uncleaned_stashed_objects.remove(stashed)

        if cleanup_failures:
            self.cleanup_error = "; ".join(cleanup_failures)
            self.state = _ArmRigTransactionState.CLEANUP_PENDING
            raise RuntimeError("Arm rig transaction commit cleanup failed: " + self.cleanup_error)
        else:
            self.cleanup_error = None
            if self.state == _ArmRigTransactionState.CLEANUP_PENDING:
                self.state = _ArmRigTransactionState.COMMITTED


_ACTIVE_TRANSACTION_STACK: List[_ArmRigTransactionContext] = []

# Task 10-B-6
# Runtime registry for committed transactions
# with unfinished resource cleanup.

_PENDING_ARM_RIG_CLEANUPS: Dict[
    str,
    "_ArmRigTransactionContext"
] = {}


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

    tx.retry_cleanup()

    if tx.state == _ArmRigTransactionState.COMMITTED:
        if (
            tx.uncleaned_stashed_objects
            or tx.uncleaned_stashed_constraints
        ):
            raise RuntimeError(
                "Cleanup reported COMMITTED "
                "while pending resources remain"
            )

        _PENDING_ARM_RIG_CLEANUPS.pop(
            tx_id,
            None
        )


def _assert_arm_rig_cleanup_gate(
    arm: bpy.types.Object,
    session_record: Optional[ArmatureSessionIdentityRecord] = None,
) -> None:
    """
    Reject new independent writes while the same Armature
    owns an unresolved committed cleanup transaction.
    """

    arm_ptr = _safe_object_pointer(
        arm,
        fallback=(session_record.registration_pointer if session_record is not None else 0),
    )
    session_id = session_record.registry_session_id if session_record is not None else None

    blocking_transactions = []

    for tx_id, tx in tuple(
        _PENDING_ARM_RIG_CLEANUPS.items()
    ):

        if tx.state != _ArmRigTransactionState.CLEANUP_PENDING:
            raise RuntimeError(
                "Arm IK cleanup registry invariant violated: "
                f"transaction {tx_id} is registered with "
                f"state {tx.state}"
            )

        if (arm_ptr and tx.arm_ptr == arm_ptr) or (
            session_id is not None and getattr(tx, "session_id", None) == session_id
        ):
            blocking_transactions.append(tx_id)

    if blocking_transactions:
        raise RuntimeError(
            "Arm IK write blocked: unresolved cleanup "
            "for the same Armature; pending transactions="
            + ",".join(sorted(blocking_transactions))
        )


def _assert_arm_rig_failed_isolation_gate(
    arm: bpy.types.Object,
    session_record: ArmatureSessionIdentityRecord,
) -> None:
    """
    Reject new independent writes while the same Armature session identity
    is isolated in _ISOLATED_FAILED_ARMATURES (FAILED-B / FAILED-C / FAILED-D).
    """
    session_id = session_record.registry_session_id
    iso_rec = _ISOLATED_FAILED_ARMATURES.get(session_id)
    if iso_rec is not None or session_record.isolation_state != _ArmatureIsolationState.NONE:
        failure_class = (
            iso_rec.get("failure_class")
            if iso_rec is not None
            else (
                _FailedTransactionClass.FAILED_D.value
                if session_record.isolation_state in (
                    _ArmatureIsolationState.TOMBSTONED_FAILED_D,
                    _ArmatureIsolationState.ARCHIVED_RETIRED,
                )
                else session_record.isolation_state.value
            )
        )
        tx_id = iso_rec.get("transaction_id", "<unknown>") if iso_rec is not None else "<unknown>"
        iso_state = (
            iso_rec.get("isolation_state")
            if iso_rec is not None
            else session_record.isolation_state.value
        )
        raise RuntimeError(
            "Arm IK write blocked: Armature session is isolated due to prior FAILED transaction "
            f"(failure_class={failure_class}, isolation_state={iso_state}, "
            f"transaction_id={tx_id}, registry_session_id={session_id})"
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
        _DEISOLATION_AUDIT_LOG.append(audit_entry)
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
        _DEISOLATION_AUDIT_LOG.append(audit_entry)
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
    _DEISOLATION_AUDIT_LOG.append(audit_entry)

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
        _DEISOLATION_AUDIT_LOG.append(audit_entry)
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
        _DEISOLATION_AUDIT_LOG.append(audit_entry)
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
    _DEISOLATION_AUDIT_LOG.append(audit_entry)

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


def _identity_failure_is_uncertain(verification: Dict[str, Any]) -> bool:
    """Keep indeterminate Blender reads separate from confirmed session invalidation."""
    return bool(
        verification.get("object_liveness_status", "UNKNOWN") == "UNKNOWN"
        or verification.get("identity_verification_uncertain", False)
    )


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
    session_rec = ensure_armature_session_identity(arm)

    # Gate 1: Reject a new outermost transaction when previous committed cleanup is unresolved
    _assert_arm_rig_cleanup_gate(arm, session_rec)

    # Gate 2: Reject a new outermost transaction when Armature session is isolated due to FAILED
    _assert_arm_rig_failed_isolation_gate(arm, session_rec)

    # Gate 3: Verify 7-condition Armature Session Identity
    admission_id_check = _verify_armature_session_identity_record(session_rec, candidate_arm=arm)
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

    tx = _ArmRigTransactionContext(arm, session_record=session_rec)
    session_rec.lifecycle_stage = "ACTIVE_TRANSACTION"
    _ACTIVE_TRANSACTION_STACK.append(tx)
    pre_snap_fp = None

    try:
        _trigger_fault_injection("during_pre_snapshot_fingerprint", {"arm": arm, "tx": tx})
        try:
            pre_snap_fp = _capture_pre_snapshot_structural_fingerprint(arm)
        except BaseException as fp_exc:
            tx.pre_write_integrity_compromised = True
            tx.pre_write_integrity_reasons = [f"Pre-snapshot fingerprint capture failed: {fp_exc}"]
            raise

        tx.state = _ArmRigTransactionState.SNAPSHOTTING
        tx.snapshot = _snapshot_arm_rig_state(arm)
        tx.state = _ArmRigTransactionState.ACTIVE

        yield tx

        if tx.rollback_only:
            raise RuntimeError(
                f"Arm rig transaction commit rejected: transaction {tx.tx_id} is marked rollback_only "
                f"(first failure reason: {tx.rollback_only_reason})"
            )

        # -------------------------------------------------------------
        # Phase 1: Reversible Commit Preparation
        # -------------------------------------------------------------
        tx.state = _ArmRigTransactionState.COMMITTING
        _trigger_fault_injection("before_commit_prepare", {"tx": tx})

        _depsgraph_update()
        _trigger_fault_injection("during_commit_prepare", {"tx": tx})

        # Verify Armature identity remained valid before Logical Commit Confirmation
        commit_id_check = _verify_armature_session_identity_record(session_rec, candidate_arm=arm)
        if not commit_id_check["is_valid"]:
            raise RuntimeError(
                "Armature session identity invalidated during COMMITTING: "
                + "; ".join(commit_id_check["reasons"])
            )

        # -------------------------------------------------------------
        # Phase 2: Logical Commit Confirmation
        # -------------------------------------------------------------
        tx.state = _ArmRigTransactionState.COMMITTED
        session_rec.lifecycle_stage = "NORMAL_TERMINAL"

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
        if tx in _ACTIVE_TRANSACTION_STACK:
            _ACTIVE_TRANSACTION_STACK.remove(tx)

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
            tx.retry_cleanup()
        except BaseException as exc:
            tx.state = _ArmRigTransactionState.CLEANUP_PENDING
            tx.cleanup_error = str(exc)
            _register_pending_arm_rig_cleanup(tx)
            raise RuntimeError(
                "Arm rig transaction committed, "
                "but post-commit cleanup failed (irreversible cleanup failed): "
                f"{exc}"
            ) from exc


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
    global _ACTIVE_TRANSACTION_STACK
    obj = bpy.data.objects.get(name)
    replaced_wrong_type = False

    if obj is not None and obj.type != "EMPTY":
        if _ACTIVE_TRANSACTION_STACK:
            # Active transaction: safely stash the doomed wrong-type object to allow complete rollback
            tx = _ACTIVE_TRANSACTION_STACK[-1]
            stashed_record = {
                "original_name": name,
                "stashed_obj": obj,
                "stashed_obj_ptr": obj.as_pointer() if hasattr(obj, "as_pointer") else None,
                "stashed_data": getattr(obj, "data", None),
                "stashed_data_ptr": getattr(obj, "data", None).as_pointer() if (getattr(obj, "data", None) and hasattr(getattr(obj, "data", None), "as_pointer")) else None,
                "stashed_data_name": getattr(obj, "data", None).name if getattr(obj, "data", None) else None,
                "collections": [c.name for c in obj.users_collection],
                "collection_refs": list(obj.users_collection),
                "collection_ptrs": [
                    c.as_pointer()
                    for c in obj.users_collection
                    if hasattr(c, "as_pointer")
                ],
                "obj_cleaned": False,
                "data_cleaned": False,
            }
            tx.stashed_objects.append(stashed_record)
            obj.name = f"__stashed_doomed_{name}__"
            for c in list(obj.users_collection):
                _authorized_unlink_object_from_collection(
                    c,
                    obj,
                    active_tx=tx,
                    category="TX_UNLINKED_ORIGINAL",
                )
            obj = None
            replaced_wrong_type = True
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
            obj = None
            replaced_wrong_type = True

    if obj is None:
        obj = bpy.data.objects.new(name, None)
        active_tx = _ACTIVE_TRANSACTION_STACK[-1] if _ACTIVE_TRANSACTION_STACK else None
        if active_tx is not None:
            active_tx.register_created_controller(obj)
        _trigger_fault_injection("get_or_create_empty_after_register", {"obj": obj, "name": name})
        _authorized_link_object_to_collection(collection, obj, active_tx=active_tx)
        obj.empty_display_type = display_type
        obj.empty_display_size = display_size
        obj.rotation_mode = "XYZ"
        if parent is not None:
            obj.parent = parent
            obj.matrix_parent_inverse = Matrix.Identity(4)
        if replaced_wrong_type:
            _trigger_fault_injection("setup_arm_ik_after_controller_replaced", {"obj": obj, "name": name})
        return obj, True

    # Existing valid Empty: ensure linked to collection via Layer 3 and update display properties
    active_tx = _ACTIVE_TRANSACTION_STACK[-1] if _ACTIVE_TRANSACTION_STACK else None
    _authorized_link_object_to_collection(collection, obj, active_tx=active_tx)
    obj.empty_display_type = display_type
    obj.empty_display_size = display_size
    return obj, False


def _apply_arm_ik_prebend_hint_side(arm: bpy.types.Object, side: str) -> None:
    """Apply a small sagittal pre-bend hint to a single arm side if currently unbent."""
    p_up = arm.pose.bones[f"upper_arm.{side}"]
    p_fore = arm.pose.bones[f"forearm.{side}"]
    p_hand = arm.pose.bones[f"hand.{side}"]

    p_up.rotation_mode = "XYZ"
    p_fore.rotation_mode = "XYZ"
    p_hand.rotation_mode = "XYZ"

    # Apply slight pre-bend only if currently zero
    euler_mag = p_up.rotation_euler.to_matrix().to_quaternion().angle
    if euler_mag < 1e-4:
        p_up.rotation_euler = Euler((math.radians(2.0), 0.0, 0.0), "XYZ")
    euler_mag_fore = p_fore.rotation_euler.to_matrix().to_quaternion().angle
    if euler_mag_fore < 1e-4:
        p_fore.rotation_euler = Euler((math.radians(4.0), 0.0, 0.0), "XYZ")


def _apply_arm_ik_prebend_hint(arm: bpy.types.Object) -> None:
    """Apply a small sagittal pre-bend hint to upper arm and forearm across both sides."""
    for side in ("L", "R"):
        _apply_arm_ik_prebend_hint_side(arm, side)


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
    valid_influence = _validate_influence(initial_influence, param_name="initial_influence")
    arm = _resolve_armature(armature_obj)

    with _arm_rig_transaction(arm):
        root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
        collection = _ensure_character_collection()

        controls: Dict[str, bpy.types.Object] = {}

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_name = ARM_IK_TARGET_NAMES[side]
            pole_name = ARM_POLE_TARGET_NAMES[side]

            ik_obj, ik_is_new = _get_or_create_empty(
                name=ik_name,
                display_type="CUBE",
                display_size=0.04,
                parent=root_obj,
                collection=collection,
            )
            if ik_is_new and side == "L":
                _trigger_fault_injection("setup_arm_ik_after_first_controller", {"ik_obj": ik_obj})
                _trigger_fault_injection("set_hand_ik_target_during_auto_init", {"ik_obj": ik_obj})

            pole_obj, pole_is_new = _get_or_create_empty(
                name=pole_name,
                display_type="SPHERE",
                display_size=0.035,
                parent=root_obj,
                collection=collection,
            )

            # Set neutral rest positions only for newly created controllers
            if ik_is_new:
                ik_obj.location = Vector((sign * SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
                ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

            if pole_is_new:
                pole_obj.location = Vector((
                    sign * (SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
                    -DEFAULT_POLE_BACKWARD_OFFSET,
                    ELBOW_REST_Z,
                ))
                pole_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

            controls[ik_name] = ik_obj
            controls[pole_name] = pole_obj

            p_up = arm.pose.bones[f"upper_arm.{side}"]
            p_fore = arm.pose.bones[f"forearm.{side}"]
            p_hand = arm.pose.bones[f"hand.{side}"]

            # Shoulder ball joint: unconstrained 3D rotation during IK
            p_up.lock_ik_x = False
            p_up.lock_ik_y = False
            p_up.lock_ik_z = False

            # Elbow hinge joint: flex on sagittal local X (positive is forward flexion)
            # Lock Y (axial twist) and Z (lateral adduction/abduction)
            p_fore.lock_ik_x = False
            p_fore.lock_ik_y = True
            p_fore.lock_ik_z = True
            p_fore.use_ik_limit_x = True
            p_fore.ik_min_x = math.radians(0.0)      # Fully extended (straight)
            p_fore.ik_max_x = math.radians(150.0)    # Maximum anatomical elbow flexion

            # Resolve or configure existing ArmIK constraint
            ik_con = None
            con_name_ik = ARM_IK_CONSTRAINT_NAMES[side]
            for idx, con in enumerate(list(p_fore.constraints)):
                if con.name == con_name_ik:
                    if con.type == "IK":
                        ik_con = con
                    else:
                        if _ACTIVE_TRANSACTION_STACK:
                            tx = _ACTIVE_TRANSACTION_STACK[-1]
                            orig_name = con.name
                            orig_mute = con.mute
                            orig_idx = idx
                            stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                            con.name = stashed_name
                            con.mute = True
                            tx.stashed_constraints.append({
                                "pbone": p_fore,
                                "con": con,
                                "con_ptr": con.as_pointer(),
                                "orig_name": orig_name,
                                "orig_mute": orig_mute,
                                "orig_idx": orig_idx,
                            })
                        else:
                            p_fore.constraints.remove(con)
                elif con.type == "IK" and con.name.startswith("ArmIK"):
                    if _ACTIVE_TRANSACTION_STACK:
                        tx = _ACTIVE_TRANSACTION_STACK[-1]
                        orig_name = con.name
                        orig_mute = con.mute
                        orig_idx = idx
                        stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                        con.name = stashed_name
                        con.mute = True
                        tx.stashed_constraints.append({
                            "pbone": p_fore,
                            "con": con,
                            "con_ptr": con.as_pointer(),
                            "orig_name": orig_name,
                            "orig_mute": orig_mute,
                            "orig_idx": orig_idx,
                        })
                    else:
                        p_fore.constraints.remove(con)

            newly_created_ik_con = False
            if ik_con is None:
                ik_con = p_fore.constraints.new(type="IK")
                ik_con.name = con_name_ik
                ik_con.influence = valid_influence
                if _ACTIVE_TRANSACTION_STACK:
                    _ACTIVE_TRANSACTION_STACK[-1].register_created_constraint(p_fore, ik_con)
                newly_created_ik_con = True

            ik_con.target = ik_obj
            ik_con.pole_target = pole_obj
            ik_con.chain_count = 2
            ik_con.use_tail = True
            ik_con.use_stretch = False
            ik_con.pole_angle = math.radians(-90.0)

            # Resolve or configure existing HandRotation constraint
            rot_con = None
            con_name_rot = HAND_ROT_CONSTRAINT_NAMES[side]
            for idx, con in enumerate(list(p_hand.constraints)):
                if con.name == con_name_rot:
                    if con.type == "COPY_ROTATION":
                        rot_con = con
                    else:
                        if _ACTIVE_TRANSACTION_STACK:
                            tx = _ACTIVE_TRANSACTION_STACK[-1]
                            orig_name = con.name
                            orig_mute = con.mute
                            orig_idx = idx
                            stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                            con.name = stashed_name
                            con.mute = True
                            tx.stashed_constraints.append({
                                "pbone": p_hand,
                                "con": con,
                                "con_ptr": con.as_pointer(),
                                "orig_name": orig_name,
                                "orig_mute": orig_mute,
                                "orig_idx": orig_idx,
                            })
                        else:
                            p_hand.constraints.remove(con)
                elif con.type == "COPY_ROTATION" and con.name.startswith("HandRotation"):
                    if _ACTIVE_TRANSACTION_STACK:
                        tx = _ACTIVE_TRANSACTION_STACK[-1]
                        orig_name = con.name
                        orig_mute = con.mute
                        orig_idx = idx
                        stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                        con.name = stashed_name
                        con.mute = True
                        tx.stashed_constraints.append({
                            "pbone": p_hand,
                            "con": con,
                            "con_ptr": con.as_pointer(),
                            "orig_name": orig_name,
                            "orig_mute": orig_mute,
                            "orig_idx": orig_idx,
                        })
                    else:
                        p_hand.constraints.remove(con)

            if rot_con is None:
                rot_con = p_hand.constraints.new(type="COPY_ROTATION")
                rot_con.name = con_name_rot
                rot_con.influence = valid_influence
                if _ACTIVE_TRANSACTION_STACK:
                    _ACTIVE_TRANSACTION_STACK[-1].register_created_constraint(p_hand, rot_con)

            rot_con.target = ik_obj
            rot_con.target_space = "WORLD"
            rot_con.owner_space = "WORLD"
            rot_con.mix_mode = "REPLACE"

            # Apply pre-bend hint only when establishing an IK chain for the first time
            if newly_created_ik_con:
                _apply_arm_ik_prebend_hint_side(arm, side)

            _trigger_fault_injection("setup_arm_ik_after_constraints_or_prebend", {"side": side, "arm": arm})

        _depsgraph_update()
        return controls


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
    valid_side = _validate_side(side, allow_both=True, param_name="side")
    valid_influence = _validate_influence(influence, param_name="influence")
    arm = _resolve_armature(armature_obj)
    sides = ("L", "R") if valid_side == "BOTH" else (valid_side,)

    with _arm_rig_transaction(arm):
        for s in sides:
            p_fore = arm.pose.bones.get(f"forearm.{s}")
            p_hand = arm.pose.bones.get(f"hand.{s}")
            if p_fore and ARM_IK_CONSTRAINT_NAMES[s] in p_fore.constraints:
                p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[s]].influence = valid_influence
            _trigger_fault_injection("set_arm_ik_influence_between_influences", {"side": s})
            if p_hand and HAND_ROT_CONSTRAINT_NAMES[s] in p_hand.constraints:
                p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[s]].influence = valid_influence
            if valid_side == "BOTH" and s == "L":
                _trigger_fault_injection("set_arm_ik_influence_between_sides", {"side": s})

        _depsgraph_update()


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
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    _depsgraph_update()

    # Preflight parent transform domains for all existing controllers on both sides BEFORE any writes
    eff_mats: Dict[str, Tuple[Optional[Matrix], Optional[Matrix]]] = {}
    for s in ("L", "R"):
        ik_c = bpy.data.objects.get(ARM_IK_TARGET_NAMES[s])
        pole_c = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[s])
        eff_ik = None
        eff_pole = None
        if ik_c is not None:
            eff_ik = compute_effective_parent_matrix(ik_c)
            validate_effective_parent_transform(eff_ik, ik_c.name)
        if pole_c is not None:
            eff_pole = compute_effective_parent_matrix(pole_c)
            validate_effective_parent_transform(eff_pole, pole_c.name)
        eff_mats[s] = (eff_ik, eff_pole)

    # All preflight checks passed; execute reset under unified transaction protection
    with _arm_rig_transaction(arm):
        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[side])
            pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[side])
            eff_ik_mat, eff_pole_mat = eff_mats[side]

            # Compute neutral targets in root/world coordinates
            ik_neutral_local = Vector((sign * SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
            pole_neutral_local = Vector((
                sign * (SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
                -DEFAULT_POLE_BACKWARD_OFFSET,
                ELBOW_REST_Z,
            ))

            if root_obj is not None:
                ik_neutral_world = root_obj.matrix_world @ ik_neutral_local
                pole_neutral_world = root_obj.matrix_world @ pole_neutral_local
                neutral_world_rot_quat = root_obj.matrix_world.to_quaternion()
            else:
                ik_neutral_world = ik_neutral_local
                pole_neutral_world = pole_neutral_local
                neutral_world_rot_quat = Quaternion()

            if ik_obj is not None and eff_ik_mat is not None:
                ik_obj.location = world_to_local_position(ik_neutral_world, eff_ik_mat)
                apply_target_rotation(ik_obj, neutral_world_rot_quat, eff_ik_mat)
                _trigger_fault_injection(f"reset_arm_ik_after_hand_controller_{side.lower()}", {"side": side, "ik_obj": ik_obj})

            if pole_obj is not None and eff_pole_mat is not None:
                pole_obj.location = world_to_local_position(pole_neutral_world, eff_pole_mat)
                apply_target_rotation(pole_obj, Quaternion(), eff_pole_mat)
                _trigger_fault_injection(f"reset_arm_ik_after_pole_{side.lower()}", {"side": side, "pole_obj": pole_obj})

            p_up = arm.pose.bones.get(f"upper_arm.{side}")
            p_fore = arm.pose.bones.get(f"forearm.{side}")
            p_hand = arm.pose.bones.get(f"hand.{side}")
            if p_up:
                p_up.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
            if p_fore:
                p_fore.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
                if ARM_IK_CONSTRAINT_NAMES[side] in p_fore.constraints:
                    p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[side]].influence = 0.0
            if p_hand:
                p_hand.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
                if HAND_ROT_CONSTRAINT_NAMES[side] in p_hand.constraints:
                    p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[side]].influence = 0.0
            _trigger_fault_injection(f"reset_arm_ik_after_influence_{side.lower()}", {"side": side})

            _apply_arm_ik_prebend_hint_side(arm, side)

        _trigger_fault_injection("reset_arm_ik_during_depsgraph_update", {"arm": arm})
        _depsgraph_update()


def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    arm = _resolve_armature(armature_obj)
    _depsgraph_update()

    p_up = arm.pose.bones[f"upper_arm.{valid_side}"]
    p_fore = arm.pose.bones[f"forearm.{valid_side}"]
    p_hand = arm.pose.bones[f"hand.{valid_side}"]

    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[valid_side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[valid_side])

    shoulder_world = arm.matrix_world @ p_up.head
    elbow_world = arm.matrix_world @ p_fore.head
    wrist_world = arm.matrix_world @ p_fore.tail
    hand_tip_world = arm.matrix_world @ p_hand.tail

    target_world = ik_obj.matrix_world.translation.copy() if ik_obj else wrist_world.copy()
    pole_world = pole_obj.matrix_world.translation.copy() if pole_obj else elbow_world.copy()

    target_error = (wrist_world - target_world).length
    upper_arm_length = (elbow_world - shoulder_world).length
    forearm_length = (wrist_world - elbow_world).length
    hand_length = (hand_tip_world - wrist_world).length
    total_arm_length = upper_arm_length + forearm_length

    # Compute interior elbow angle
    v_up = (shoulder_world - elbow_world).normalized()
    v_fore = (wrist_world - elbow_world).normalized()
    cos_angle = max(-1.0, min(1.0, v_up.dot(v_fore)))
    elbow_interior_deg = math.degrees(math.acos(cos_angle))
    elbow_flexion_deg = 180.0 - elbow_interior_deg

    # Hand orientation inspection
    hand_w_mat = (arm.matrix_world @ p_hand.matrix).to_3x3()
    hand_world_euler = tuple(round(math.degrees(a), 4) for a in hand_w_mat.to_euler("XYZ"))

    if ik_obj:
        target_quat = ik_obj.matrix_world.to_quaternion()
        target_world_euler = tuple(round(math.degrees(a), 4) for a in target_quat.to_euler("XYZ"))
        rot_diff = target_quat.rotation_difference(hand_w_mat.to_quaternion()).angle
        rotation_error_deg = round(math.degrees(rot_diff), 4)
    else:
        target_world_euler = hand_world_euler
        rotation_error_deg = 0.0

    ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[valid_side])
    rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[valid_side])
    ik_influence = ik_con.influence if ik_con else 0.0
    rot_influence = rot_con.influence if rot_con else 0.0

    return {
        "side": valid_side,
        "shoulder_world": shoulder_world,
        "elbow_world": elbow_world,
        "wrist_world": wrist_world,
        "hand_tip_world": hand_tip_world,
        "target_world": target_world,
        "pole_world": pole_world,
        "target_error": target_error,
        "hand_world_euler_deg": hand_world_euler,
        "target_world_euler_deg": target_world_euler,
        "rotation_error_deg": rotation_error_deg,
        "upper_arm_length": upper_arm_length,
        "forearm_length": forearm_length,
        "hand_length": hand_length,
        "total_arm_length": total_arm_length,
        "elbow_flexion_deg": elbow_flexion_deg,
        "ik_influence": ik_influence,
        "rot_influence": rot_influence,
    }


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
    - Case C: Object exists but type != 'EMPTY' -> it will be unlinked and recreated by _get_or_create_empty();
      anticipate the expected effective parent matrix for the new EMPTY, NOT the doomed object's matrix.

    Returns:
        (needs_auto_init, eff_ik_mat, eff_pole_mat)
    """
    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[valid_side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[valid_side])
    ik_valid = (ik_obj is not None and ik_obj.type == "EMPTY")
    pole_valid = (pole_obj is not None and pole_obj.type == "EMPTY")
    needs_auto_init = not (ik_valid and pole_valid)

    expected_new_eff_mat = (
        root_obj.matrix_world @ Matrix.Identity(4)
        if root_obj is not None
        else Matrix.Identity(4)
    )

    if needs_auto_init:
        # setup_arm_ik() processes all four controllers (L and R);
        # validate effective parent transforms for existing valid controls and anticipated new controls.
        other_side = "R" if valid_side == "L" else "L"
        all_ctrl_names = (
            ARM_IK_TARGET_NAMES[valid_side],
            ARM_POLE_TARGET_NAMES[valid_side],
            ARM_IK_TARGET_NAMES[other_side],
            ARM_POLE_TARGET_NAMES[other_side],
        )
        for ctrl_name in all_ctrl_names:
            existing_obj = bpy.data.objects.get(ctrl_name)
            if existing_obj is not None and existing_obj.type == "EMPTY":
                # Case A: Existing valid EMPTY controller
                ctrl_eff_mat = compute_effective_parent_matrix(existing_obj)
            else:
                # Case B (missing) & Case C (wrong type, will be unlinked/recreated):
                # Use expected effective parent matrix for the new Empty
                ctrl_eff_mat = expected_new_eff_mat
            validate_effective_parent_transform(ctrl_eff_mat, ctrl_name)

        eff_ik_mat = (
            compute_effective_parent_matrix(ik_obj)
            if ik_valid
            else expected_new_eff_mat
        )
        eff_pole_mat = (
            compute_effective_parent_matrix(pole_obj)
            if pole_valid
            else expected_new_eff_mat
        )
    else:
        # Both target controllers exist and are valid EMPTY objects; validate their transforms directly
        eff_ik_mat = compute_effective_parent_matrix(ik_obj)
        eff_pole_mat = compute_effective_parent_matrix(pole_obj)
        validate_effective_parent_transform(eff_ik_mat, ik_obj.name)
        validate_effective_parent_transform(eff_pole_mat, pole_obj.name)

    return needs_auto_init, eff_ik_mat, eff_pole_mat


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
    # Phase A: User input pre-validation (all inputs validated before scene mutation or auto-init)
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    valid_world_xyz = _validate_vec3(world_xyz, param_name="world_xyz", allow_none=False)
    valid_hand_rot = _validate_vec3(hand_rotation_deg, param_name="hand_rotation_deg", allow_none=True)
    valid_pole_world = _validate_vec3(pole_world_xyz, param_name="pole_world_xyz", allow_none=True)
    valid_clamp_reach = _validate_bool(clamp_reach, param_name="clamp_reach")
    valid_influence = _validate_influence(influence, param_name="influence")

    # Phase B: Zero-mutation controller and environment preflight
    arm = _resolve_armature(armature_obj)
    _depsgraph_update()
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")

    needs_auto_init, eff_ik_mat, eff_pole_mat = _preflight_arm_ik_parent_transforms(
        arm, valid_side, root_obj
    )

    # Phase B2: Zero-mutation derived spatial coordinate and orientation preflight
    p_up = arm.pose.bones[f"upper_arm.{valid_side}"]
    p_fore = arm.pose.bones[f"forearm.{valid_side}"]
    p_hand = arm.pose.bones[f"hand.{valid_side}"]

    shoulder_world = arm.matrix_world @ p_up.head

    requested = Vector(valid_world_xyz)
    applied = requested.copy()
    clamped_reach = False

    vec_from_shoulder = applied - shoulder_world
    dist = vec_from_shoulder.length
    is_reachable = (MIN_ARM_REACH <= dist <= MAX_ARM_REACH)

    # Reach clamping relative to shoulder joint
    if valid_clamp_reach:
        if dist > MAX_ARM_REACH:
            clamped_reach = True
            if dist > 1e-6:
                applied = shoulder_world + vec_from_shoulder.normalized() * MAX_ARM_REACH
            else:
                applied = shoulder_world + Vector((0.0, 0.0, -1.0)) * MAX_ARM_REACH
        elif dist < MIN_ARM_REACH:
            clamped_reach = True
            direction = vec_from_shoulder.normalized() if dist > 1e-6 else Vector((0.0, 0.0, -1.0))
            applied = shoulder_world + direction * MIN_ARM_REACH

    # Elbow pole target positioning in world space
    sign = -1.0 if valid_side == "L" else 1.0
    if valid_pole_world is not None:
        pole_world = Vector(valid_pole_world)
    else:
        # Default pole placement: behind (-Y) and slightly outward (X)
        mid_pt = 0.5 * (shoulder_world + applied)
        pole_world = Vector((
            mid_pt.x + sign * DEFAULT_POLE_OUTWARD_OFFSET,
            min(shoulder_world.y, applied.y) - DEFAULT_POLE_BACKWARD_OFFSET,
            mid_pt.z,
        ))

    # Hand 3D orientation target in world coordinates
    if valid_hand_rot is not None:
        target_world_rot_quat = Euler((math.radians(v) for v in valid_hand_rot), "XYZ").to_quaternion()
    else:
        # Neutral level orientation matching CharacterRoot
        if root_obj is not None:
            target_world_rot_quat = root_obj.matrix_world.to_quaternion()
        else:
            target_world_rot_quat = Quaternion()

    ik_local_pos = world_to_local_position(applied, eff_ik_mat)
    pole_local_pos = world_to_local_position(pole_world, eff_pole_mat)
    ik_local_rot_quat = world_to_local_rotation_quaternion(target_world_rot_quat, eff_ik_mat)

    # Phase B3: Verify all derived spatial coordinates and orientations are strictly finite
    for v in (applied, pole_world, ik_local_pos, pole_local_pos):
        for coord in v:
            if not math.isfinite(coord):
                raise ValueError(f"Derived coordinate {coord!r} in target computation is not finite")
    for q_comp in target_world_rot_quat:
        if not math.isfinite(q_comp):
            raise ValueError(f"Derived orientation component {q_comp!r} is not finite")
    for q_comp in ik_local_rot_quat:
        if not math.isfinite(q_comp):
            raise ValueError(f"Derived local orientation component {q_comp!r} is not finite")

    # Phase C & Phase D: Transaction snapshot & atomic commit
    with _arm_rig_transaction(arm):
        if needs_auto_init:
            setup_arm_ik(arm, initial_influence=valid_influence)

        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES[valid_side]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES[valid_side]]

        _apply_arm_ik_prebend_hint_side(arm, valid_side)

        # Convert applied world targets to controller local spaces preserving rotation_mode
        ik_obj.location = ik_local_pos
        _trigger_fault_injection("set_hand_ik_target_after_hand_location", {"ik_obj": ik_obj})

        apply_target_rotation(ik_obj, target_world_rot_quat, eff_ik_mat)
        _trigger_fault_injection("set_hand_ik_target_after_hand_rotation", {"ik_obj": ik_obj})

        pole_obj.location = pole_local_pos
        _trigger_fault_injection("set_hand_ik_target_after_pole_location", {"pole_obj": pole_obj})

        # Update constraint influence
        ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[valid_side])
        if ik_con:
            ik_con.influence = valid_influence
        _trigger_fault_injection("set_hand_ik_target_between_influences", {"ik_con": ik_con})

        rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[valid_side])
        if rot_con:
            rot_con.influence = valid_influence
        _trigger_fault_injection("set_hand_ik_target_after_rot_influence", {"rot_con": rot_con})

        _update_arm_ik_depsgraph()

        _trigger_fault_injection("set_hand_ik_target_during_state_read", {"arm": arm})
        state = get_arm_ik_state(arm, valid_side)
        state["requested_world"] = requested
        state["applied_world"] = applied
        state["is_reachable"] = is_reachable
        state["clamped_reach"] = clamped_reach

    return state
