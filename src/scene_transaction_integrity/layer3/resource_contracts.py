"""Resource contract exception and matrix equality helper migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3)."""

from typing import Any


class ExternalControllerNameConflictError(RuntimeError, ValueError):
    """Raised when a controller name is occupied by an external/pre-existing non-EMPTY object (F14-05)."""
    pass


def _matrix_equals(m1: Any, m2: Any, tol: float = 1e-5) -> bool:
    """Check element-wise matrix equality within specified tolerance."""
    if m1 is None or m2 is None:
        return m1 is m2
    try:
        for r in range(4):
            for c in range(4):
                if abs(float(m1[r][c]) - float(m2[r][c])) > tol:
                    return False
        return True
    except (IndexError, TypeError, ValueError):
        return False
