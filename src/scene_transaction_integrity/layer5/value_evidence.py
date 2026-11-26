"""Read-only value evidence helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 5)."""

import math
from typing import Any

import bpy
from mathutils import Color, Euler, Matrix, Quaternion, Vector


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
