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


# [INTRODUCED 2026-11-24T20:21:00+08:00]
# NODE: 10-B / L3-12
# FUNCTION: _cleanup_failed_character_collection_registration
# PURPOSE: 在 ACTIVE 事务下对尚未完成可信登记且无外部依赖的新建 Character Collection 执行局部删除补偿与删后核验，若已完整登记则提前返回交由事务回滚
# REASON: 将 Collection 局部创建失败补偿从 arm_ik.py 归入既有 Layer 3 Collection 创建模块，保留原兼容入口及所有外部依赖与凭证边界
def _cleanup_failed_character_collection_registration(
    col: bpy.types.Collection,
    expected_ptr: int,
    initial_parent: bpy.types.Collection,
    active_tx: Any,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    find_live_collection_by_identity: Callable[..., Any],
    is_child_collection_linked_by_identity: Callable[..., bool],
) -> None:
    """Compensate only an unregistered, proven-fresh Collection.

    Once a valid creation receipt exists, the enclosing transaction owns the
    deletion and will perform its authorized rollback. Never remove that
    Collection here or leave a stale receipt pointing at a destroyed ID.
    """
    if (not active_transaction_stack
            or active_transaction_stack[-1] is not active_tx
            or active_tx.state != transaction_state_cls.ACTIVE):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: transaction not ACTIVE")
    if (type(expected_ptr) is not int or expected_ptr <= 0
            or not isinstance(active_tx.entry_collection_ptrs, (set, frozenset))
            or expected_ptr in active_tx.entry_collection_ptrs):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: creation baseline invalid")
    registry = active_tx.created_collections
    receipts = active_tx._collection_creation_receipts
    if (not isinstance(registry, list) or not isinstance(receipts, dict)
            or any(not isinstance(rec, dict) for rec in registry)):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: registry malformed")
    try:
        ptr = int(col.as_pointer())
        parent_ptr = int(initial_parent.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: identity unreadable") from exc
    if (ptr != expected_ptr or parent_ptr <= 0
            or find_live_collection_by_identity(col, expected_ptr) is None
            or find_live_collection_by_identity(initial_parent, parent_ptr) is None):
        raise RuntimeError("COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: original identity lost")

    records = [rec for rec in registry if rec.get("col_ptr") == expected_ptr]
    receipt = receipts.get(expected_ptr)
    if records or receipt is not None:
        # The receipt+registry pair is authoritative after successful
        # registration. Let the enclosing transaction remove it exactly once.
        if (len(records) != 1 or not isinstance(receipt, tuple) or len(receipt) != 5
                or records[0].get("col_ref") != col
                or records[0].get("initial_parent") != initial_parent
                or records[0].get("initial_parent_ptr") != parent_ptr
                or receipt[0] != col or receipt[1] != initial_parent
                or receipt[2] != active_tx.session_id
                or receipt[3] != active_tx.tx_id
                or receipt[4] is not active_tx._collection_receipt_seal):
            raise RuntimeError(
                "COLLECTION_CREATION_CLEANUP_AUTHORITY_UNPROVEN: partial or mismatched registration"
            )
        return

    # This is the small gap between bpy.data.collections.new() and successful
    # registration. Only the exact unlinked newly returned ID may be removed.
    if (not any(c == col and int(c.as_pointer()) == expected_ptr
                for c in bpy.data.collections)
            or int(col.users) != 0
            or len(col.objects) != 0
            or len(col.children) != 0):
        raise RuntimeError(
            "COLLECTION_CREATION_CLEANUP_REFUSED: unregistered Collection has external dependencies"
        )
    # Avoid removing a Collection that became a child of some other parent,
    # even if a mocked/inconsistent Blender user counter erroneously says zero.
    for parent in bpy.data.collections:
        if parent != col and is_child_collection_linked_by_identity(parent, col, expected_ptr):
            raise RuntimeError("COLLECTION_CREATION_CLEANUP_REFUSED: Collection gained a parent")
    for scene in bpy.data.scenes:
        if is_child_collection_linked_by_identity(scene.collection, col, expected_ptr):
            raise RuntimeError("COLLECTION_CREATION_CLEANUP_REFUSED: Collection gained a scene parent")

    try:
        bpy.data.collections.remove(col)
    except BaseException as exc:
        raise RuntimeError(
            f"COLLECTION_CREATION_CLEANUP_REMOVE_FAILED: ptr={expected_ptr}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if find_live_collection_by_identity(col, expected_ptr) is not None:
        raise RuntimeError(
            f"COLLECTION_CREATION_CLEANUP_REMOVE_UNVERIFIED: ptr={expected_ptr} still live"
        )
