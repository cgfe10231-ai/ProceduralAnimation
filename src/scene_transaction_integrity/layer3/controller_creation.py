"""Empty controller creation and reuse entry migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-04)."""

from typing import Any, Callable, Dict, List, Optional, Tuple

import bpy

from src.scene_transaction_integrity.layer3.resource_contracts import (
    ExternalControllerNameConflictError,
)


def _get_or_create_empty(
    name: str,
    display_type: str,
    display_size: float,
    parent: Optional[bpy.types.Object],
    collection: bpy.types.Collection,
    *,
    active_transaction_stack: List[Any],
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    verify_transaction_wrong_type_object_ownership: Callable[..., bool],
    authorized_unlink_object_from_collection: Callable[..., Optional[Dict[str, Any]]],
    authorized_link_object_to_collection: Callable[..., Optional[Dict[str, Any]]],
    authorized_assign_object_parent: Callable[..., Optional[Dict[str, Any]]],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    matrix_cls: Any,
) -> Tuple[bpy.types.Object, bool]:
    """Retrieve or construct an Empty control object preserving existing parent and transform.

    Returns:
        Tuple (obj, is_new): obj is the Empty object, is_new indicates whether it was created fresh.
    """
    obj = bpy.data.objects.get(name)
    # Do not adopt an existing EMPTY simply because its global name matches.
    if obj is not None:
        tx = active_transaction_stack[-1] if active_transaction_stack else None
        if tx is None:
            raise RuntimeError('Controller lookup requires an active Arm IK transaction')
        require_existing_arm_ik_controller_ownership(tx.arm, scope='_get_or_create_empty')
    replaced_wrong_type = False

    if obj is not None and obj.type != "EMPTY":
        active_tx = active_transaction_stack[-1] if active_transaction_stack else None
        target_arm = active_tx.arm if active_tx is not None else None
        if not verify_transaction_wrong_type_object_ownership(obj, active_tx, target_arm):
            raise ExternalControllerNameConflictError(
                f"EXTERNAL_CONTROLLER_NAME_CONFLICT: Controller '{name}' matches an existing non-EMPTY "
                f"object '{obj.name}' (type='{obj.type}', ptr={obj.as_pointer() if hasattr(obj, 'as_pointer') else 'None'}) "
                f"that is not owned by the active transaction."
            )

        tx = active_tx
        stashed_record = {
            "original_name": name,
            "stashed_obj": obj,
            "stashed_obj_ptr": obj.as_pointer() if hasattr(obj, "as_pointer") else None,
            "stashed_data": getattr(obj, "data", None),
            "stashed_data_ptr": getattr(obj, "data", None).as_pointer() if (getattr(obj, "data", None) and hasattr(getattr(obj, "data", None), "as_pointer")) else None,
            "stashed_data_name": getattr(obj, "data", None).name if getattr(obj, "data", None) else None,
            "collections": [c.name for c in obj.users_collection],
            "collection_refs": list(obj.users_collection),
            "collection_ptrs": [
                c.as_pointer()
                for c in obj.users_collection
                if hasattr(c, "as_pointer")
            ],
            "obj_cleaned": False,
            "data_cleaned": False,
        }
        tx.stashed_objects.append(stashed_record)
        obj.name = f"__stashed_doomed_{name}__"
        for c in list(obj.users_collection):
            authorized_unlink_object_from_collection(
                c,
                obj,
                active_tx=tx,
                category="TX_UNLINKED_ORIGINAL",
            )
        obj = None
        replaced_wrong_type = True

    if obj is None:
        obj = bpy.data.objects.new(name, None)
        active_tx = active_transaction_stack[-1] if active_transaction_stack else None
        if active_tx is not None:
            active_tx.register_created_controller(obj)
        trigger_fault_injection("get_or_create_empty_after_register", {"obj": obj, "name": name})
        authorized_link_object_to_collection(collection, obj, active_tx=active_tx)
        obj.empty_display_type = display_type
        obj.empty_display_size = display_size
        obj.rotation_mode = "XYZ"
        if parent is not None:
            authorized_assign_object_parent(
                obj=obj,
                parent=parent,
                matrix_parent_inverse=matrix_cls.Identity(4),
                active_tx=active_tx,
            )
        if replaced_wrong_type:
            trigger_fault_injection("setup_arm_ik_after_controller_replaced", {"obj": obj, "name": name})
        return obj, True

    # Existing valid Empty: ensure linked to collection via Layer 3 and update display properties
    active_tx = active_transaction_stack[-1] if active_transaction_stack else None
    authorized_link_object_to_collection(collection, obj, active_tx=active_tx)
    obj.empty_display_type = display_type
    obj.empty_display_size = display_size
    return obj, False
