"""Pure input validation helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4)."""

import math
from typing import Any, Optional, Tuple


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
