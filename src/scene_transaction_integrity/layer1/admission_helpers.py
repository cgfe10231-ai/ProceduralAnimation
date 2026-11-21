"""Admission and object name/uncertainty helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1)."""

from typing import Any, Dict


def _safe_object_name(obj: Any, fallback: str = "<invalid_or_destroyed_object>") -> str:
    """Safely read a Blender object's name without raising ReferenceError."""
    if obj is None:
        return fallback
    try:
        return str(obj.name)
    except BaseException:
        return fallback


def _identity_failure_is_uncertain(verification: Dict[str, Any]) -> bool:
    """Keep indeterminate Blender reads separate from confirmed session invalidation."""
    return bool(
        verification.get("object_liveness_status", "UNKNOWN") == "UNKNOWN"
        or verification.get("identity_verification_uncertain", False)
    )
