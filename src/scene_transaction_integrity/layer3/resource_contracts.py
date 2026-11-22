"""Resource contract exception and matrix equality helper migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3)."""

from typing import Any, Dict, Optional

import bpy


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


_TARGET_UNSET = object()

ARM_IK_CONSTRAINT_NAMES: Dict[str, str] = {"L": "ArmIK.L", "R": "ArmIK.R"}


def _controller_constraint_binding_proven(
    arm: bpy.types.Object,
    obj: bpy.types.Object,
    role: tuple[str, str],
    snapshot: Optional[Dict[str, Any]] = None,
) -> bool:
    """Prove the target Armature owns the original IK relationship by identity.

    The transaction snapshot is read for rollback-time provenance, because the
    live constraint target may already have been changed by the transaction.
    An existing object with a familiar name or parent is not proof of a binding.
    """
    side, field = role
    try:
        pbone = arm.pose.bones.get(f'forearm.{side}')
        if pbone is None:
            return False
        constraint = pbone.constraints.get(ARM_IK_CONSTRAINT_NAMES[side])
        if constraint is None or constraint.type != 'IK':
            return False
        if snapshot is None:
            bound = getattr(constraint, field, None)
            return bound is not None and int(bound.as_pointer()) == int(obj.as_pointer()) and bound == obj
        saved_bone = snapshot.get('pose_bones', {}).get(f'forearm.{side}', {})
        for saved in saved_bone.get('constraints', ()):
            if (saved.get('name') != ARM_IK_CONSTRAINT_NAMES[side]
                    or saved.get('type') != 'IK'):
                continue
            if saved.get('con_ptr') != int(constraint.as_pointer()):
                continue
            if saved.get('con_ref') != constraint:
                continue
            bound = saved.get(field)
            return bound is not None and int(bound.as_pointer()) == int(obj.as_pointer()) and bound == obj
    except (AttributeError, KeyError, ReferenceError, TypeError, ValueError):
        return False
    return False


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
