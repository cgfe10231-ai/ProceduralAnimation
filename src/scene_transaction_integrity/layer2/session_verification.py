"""Armature session identity 7-condition verification migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-02)."""

from typing import Any, Dict, List, Optional

import bpy

from src.scene_transaction_integrity.layer2.identity_helpers import (
    _check_original_object_liveness,
)
from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
)


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
