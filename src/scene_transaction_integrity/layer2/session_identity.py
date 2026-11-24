"""Armature session identity resolution and registration migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-03)."""

import uuid

import bpy

from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _MANAGED_ARMATURE_IDENTITIES,
)
from src.scene_transaction_integrity.layer2.session_verification import (
    _verify_armature_session_identity_record,
)


def ensure_armature_session_identity(
    arm: bpy.types.Object,
) -> ArmatureSessionIdentityRecord:
    """Layer 2: Resolve existing verified ArmatureSessionIdentityRecord or register a new session identity."""
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
