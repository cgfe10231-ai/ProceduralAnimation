"""Session identity pointer and liveness helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from typing import Any, Dict, Optional

import bpy

from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)


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
