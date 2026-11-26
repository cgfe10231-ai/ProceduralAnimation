"""Arm IK effective parent transform preflight migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-03)."""

from typing import Any, Callable, Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix

from src.scene_transaction_integrity.layer3 import ExternalControllerNameConflictError


def _preflight_arm_ik_parent_transforms(
    arm: bpy.types.Object,
    valid_side: str,
    root_obj: Optional[bpy.types.Object],
    *,
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    verify_transaction_wrong_type_object_ownership: Callable[..., bool],
    active_transaction_stack: List[Any],
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    compute_effective_parent_matrix: Callable[[bpy.types.Object], Matrix],
    validate_effective_parent_transform: Callable[[Matrix, str], None],
) -> Tuple[bool, Matrix, Matrix]:
    """Preflight check effective parent transform domains before any scene mutation (Task 10-B-2 & 10-B-3).

    Inspects existing and anticipated arm IK controllers without writing to the scene.
    A controller is valid if and only if the object exists and its type is 'EMPTY'.
    If any controller on valid_side is missing or not an EMPTY, setup_arm_ik() will be required.

    Preflight rules:
    - Case A: Existing object is an EMPTY -> compute actual effective parent matrix.
    - Case B: Object does not exist -> compute expected effective parent matrix (root_obj @ Identity).
    - Case C: Object exists but type != 'EMPTY' -> must be a verified transaction-owned controller (F14-05);
      unowned non-EMPTY objects are rejected with EXTERNAL_CONTROLLER_NAME_CONFLICT before scene writes.

    Returns:
        (needs_auto_init, eff_ik_mat, eff_pole_mat)
    """
    require_existing_arm_ik_controller_ownership(arm, scope='_preflight_arm_ik_parent_transforms')
    ik_obj = bpy.data.objects.get(arm_ik_target_names[valid_side])
    pole_obj = bpy.data.objects.get(arm_pole_target_names[valid_side])
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
        active_tx = active_transaction_stack[-1] if active_transaction_stack else None
        other_side = "R" if valid_side == "L" else "L"
        all_ctrl_names = (
            arm_ik_target_names[valid_side],
            arm_pole_target_names[valid_side],
            arm_ik_target_names[other_side],
            arm_pole_target_names[other_side],
        )
        for ctrl_name in all_ctrl_names:
            existing_obj = bpy.data.objects.get(ctrl_name)
            if existing_obj is not None and existing_obj.type != "EMPTY":
                if not verify_transaction_wrong_type_object_ownership(existing_obj, active_tx, arm):
                    raise ExternalControllerNameConflictError(
                        f"EXTERNAL_CONTROLLER_NAME_CONFLICT: Controller '{ctrl_name}' matches pre-existing or external "
                        f"non-EMPTY object '{existing_obj.name}' (type='{existing_obj.type}') not owned by active transaction."
                    )
            if existing_obj is not None and existing_obj.type == "EMPTY":
                # Case A: Existing valid EMPTY controller
                ctrl_eff_mat = compute_effective_parent_matrix(existing_obj)
            else:
                # Case B (missing) or verified transaction-created replacement:
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
