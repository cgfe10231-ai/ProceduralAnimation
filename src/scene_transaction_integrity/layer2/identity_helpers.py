"""Session identity pointer helper migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2)."""

from typing import Any


def _safe_object_pointer(obj: Any, fallback: int = 0) -> int:
    """Safely read a Blender object's RNA pointer without raising ReferenceError."""
    if obj is None:
        return fallback
    try:
        return int(obj.as_pointer())
    except BaseException:
        return fallback
