from typing import Any, Callable, Dict, List, Optional

import bpy

from src.scene_transaction_integrity.layer3.collection_queries import (
    _is_child_collection_linked_by_identity,
)


def _find_live_collection_by_identity(
    col_ref: Optional[bpy.types.Collection],
    expected_ptr: Optional[int],
) -> Optional[bpy.types.Collection]:
    """Resolve the original live Blender Collection (user or scene master collection) by identity.

    A matching name alone never proves identity.
    """
    if col_ref is None and expected_ptr is None:
        return None

    if col_ref is not None:
        try:
            ref_ptr = col_ref.as_pointer()
        except ReferenceError:
            return None
        if expected_ptr is not None and ref_ptr != expected_ptr:
            return None
        target_ptr = expected_ptr if expected_ptr is not None else ref_ptr
    else:
        target_ptr = expected_ptr

    for candidate in bpy.data.collections:
        try:
            if candidate.as_pointer() != target_ptr:
                continue
            if col_ref is None or candidate == col_ref:
                return candidate
        except ReferenceError:
            continue

    if bpy.context and getattr(bpy.context, "scene", None) and getattr(bpy.context.scene, "collection", None):
        sc = bpy.context.scene.collection
        try:
            if sc.as_pointer() == target_ptr and (col_ref is None or sc == col_ref):
                return sc
        except ReferenceError:
            pass

    for scene in bpy.data.scenes:
        sc = getattr(scene, "collection", None)
        if sc is None:
            continue
        try:
            if sc.as_pointer() == target_ptr and (col_ref is None or sc == col_ref):
                return sc
        except ReferenceError:
            continue

    return None


def _ensure_character_collection(
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    cleanup_failed_character_collection_registration: Callable[
        [bpy.types.Collection, Optional[int], bpy.types.Collection, Any],
        None,
    ],
    authorized_link_child_collection: Callable[..., Optional[Dict[str, Any]]],
) -> bpy.types.Collection:
    """Ensure the Character collection exists in the active scene with strict registration-before-link order (F14-06)."""
    scene = bpy.context.scene
    col = bpy.data.collections.get("Character")
    if col is not None:
        return col

    active_tx = active_transaction_stack[-1] if active_transaction_stack else None
    if active_tx is None or active_tx.state != transaction_state_cls.ACTIVE:
        raise RuntimeError("Cannot create Character collection: must be within an ACTIVE transaction")

    col = bpy.data.collections.new("Character")
    new_col_ptr = col.as_pointer() if hasattr(col, "as_pointer") else None

    # Step 1: Fault injection point: character_collection_before_registration
    try:
        trigger_fault_injection("character_collection_before_registration", {"col": col, "col_ptr": new_col_ptr, "scene": scene})
    except BaseException as creation_exc:
        try:
            cleanup_failed_character_collection_registration(
                col, new_col_ptr, scene.collection, active_tx,
            )
        except BaseException as cleanup_exc:
            # Both failures must survive reporting. Never turn a failed
            # compensating deletion into an ordinary registration error.
            raise RuntimeError(
                "COLLECTION_CREATION_CLEANUP_FAILED: "
                f"original={type(creation_exc).__name__}: {creation_exc}; "
                f"cleanup={type(cleanup_exc).__name__}: {cleanup_exc}"
            ) from cleanup_exc
        raise

    # Step 2: Immediate identity registration
    try:
        active_tx.register_created_collection(col, initial_parent=scene.collection)
        reg = active_tx.created_collections[-1] if active_tx.created_collections else None
        if reg is None or reg.get("col_ref") != col or reg.get("col_ptr") != new_col_ptr:
            raise RuntimeError("Failed to verify Character collection identity registration")
    except BaseException as creation_exc:
        try:
            cleanup_failed_character_collection_registration(
                col, new_col_ptr, scene.collection, active_tx,
            )
        except BaseException as cleanup_exc:
            # Both failures must survive reporting. Never turn a failed
            # compensating deletion into an ordinary registration error.
            raise RuntimeError(
                "COLLECTION_CREATION_CLEANUP_FAILED: "
                f"original={type(creation_exc).__name__}: {creation_exc}; "
                f"cleanup={type(cleanup_exc).__name__}: {cleanup_exc}"
            ) from cleanup_exc
        raise

    # Step 3: Fault injection point: character_collection_after_registration_before_link
    trigger_fault_injection("character_collection_after_registration_before_link", {"col": col, "col_ptr": new_col_ptr, "scene": scene})

    # Step 4: Authorized link to scene via Layer 3 (F14-02 / Task 10-B-15 4/6)
    authorized_link_child_collection(scene.collection, col, active_tx=active_tx)

    # Step 5: Verify parent-child relationship genuinely exists
    if not _is_child_collection_linked_by_identity(scene.collection, col, new_col_ptr):
        raise RuntimeError("Failed to verify Character collection scene linkage")

    # Step 6: Fault injection point: character_collection_after_link
    trigger_fault_injection("character_collection_after_link", {"col": col, "col_ptr": new_col_ptr, "scene": scene})

    return col
