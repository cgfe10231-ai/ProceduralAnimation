"""Collection creation receipt registration migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-06)."""

from typing import Any, Callable, Optional

import bpy

from src.scene_transaction_integrity.layer2.session_registries import (
    _MANAGED_ARMATURE_IDENTITIES,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)


# [INTRODUCED 2026-11-23T18:52:00+08:00]
# NODE: 10-B / L2-06
# FUNCTION: _register_created_collection
# PURPOSE: Attest a newly created, not-yet-linked Collection and its intended parent with atomic ledger/receipt registration and local rollback verification in Layer 2
# REASON: Authorized L2-06 migration of _ArmRigTransactionContext.register_created_collection along the normal asset creation path while preserving original identity checks, receipts, and explicit Layer 3 collection lookup callback
def _register_created_collection(
    self: Any,
    col: bpy.types.Collection,
    initial_parent: Optional[bpy.types.Collection] = None,
    *,
    find_live_collection_by_identity: Callable[
        [Optional[bpy.types.Collection], Optional[int]],
        Optional[bpy.types.Collection],
    ],
) -> None:
    """Attest a newly created, not-yet-linked Collection and intended parent."""
    if (self.state != _ArmRigTransactionState.ACTIVE
            or not _ACTIVE_TRANSACTION_STACK
            or _ACTIVE_TRANSACTION_STACK[-1] is not self):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: registration requires owning ACTIVE transaction")
    if not isinstance(self.entry_collection_ptrs, (set, frozenset)):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: missing entry Collection baseline")
    if (self.session_record is None
            or _MANAGED_ARMATURE_IDENTITIES.get(self.session_id) is not self.session_record
            or self.session_record.original_blender_ref is not self.arm):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: Armature session provenance mismatch")
    try:
        col_ptr = int(col.as_pointer())
        live_col = find_live_collection_by_identity(col, col_ptr)
        in_datablocks = any(c.as_pointer() == col_ptr and c == col for c in bpy.data.collections)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: Collection identity unreadable") from exc
    if (col_ptr <= 0 or live_col is None or not in_datablocks
            or col_ptr in self.entry_collection_ptrs):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: Collection was not created after transaction entry")
    if col.users != 0:
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: register before any Collection link")
    if initial_parent is None:
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: initial parent required")
    try:
        parent_ptr = int(initial_parent.as_pointer())
        live_parent = find_live_collection_by_identity(initial_parent, parent_ptr)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: original parent identity unreadable") from exc
    if parent_ptr <= 0 or live_parent is None:
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: original parent is not live")
    scene = bpy.context.scene if bpy.context else None
    is_current_scene_root = (scene is not None and scene.collection == initial_parent
                             and int(scene.collection.as_pointer()) == parent_ptr)
    is_tx_created_parent = any(
        r.get("col_ref") == initial_parent and r.get("col_ptr") == parent_ptr
        and parent_ptr in self._collection_creation_receipts
        and self._collection_creation_receipts[parent_ptr][0] == initial_parent
        and self._collection_creation_receipts[parent_ptr][4] is self._collection_receipt_seal
        for r in self.created_collections if isinstance(r, dict)
    )
    if not (is_current_scene_root or is_tx_created_parent):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: parent outside owned Collection hierarchy")
    if col_ptr in self._collection_creation_receipts or any(
            isinstance(r, dict) and r.get("col_ptr") == col_ptr
            for r in self.created_collections):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: duplicate Collection registration")
    # [INTRODUCED 2026-11-16T21:33:00+08:00]
    # FUNCTION: _ArmRigTransactionContext.register_created_collection
    # PURPOSE: Guarantee atomic in-memory consistency between created_collections registry and _collection_creation_receipts
    # REASON: Task 10-B fix-5 (R2-TAIL-02), prevent unilateral collection registration record without matching receipt on failure
    registry = getattr(self, "created_collections", None)
    receipts = getattr(self, "_collection_creation_receipts", None)
    seal = getattr(self, "_collection_receipt_seal", None)
    session_id = getattr(self, "session_id", None)
    tx_id = getattr(self, "tx_id", None)
    if (not isinstance(registry, list)
            or not isinstance(receipts, dict)
            or seal is None
            or not isinstance(session_id, str) or not session_id
            or not isinstance(tx_id, str) or not tx_id):
        raise RuntimeError("COLLECTION_OWNERSHIP_UNPROVEN: registration ledger or session metadata unavailable")

    record = {
        "col_ref": col,
        "col_ptr": col_ptr,
        "created_name": col.name,
        "initial_parent": initial_parent,
        "initial_parent_ptr": parent_ptr,
    }
    receipt = (
        col, initial_parent, session_id, tx_id, seal,
    )

    registry_appended = False
    try:
        registry.append(record)
        registry_appended = True
        receipts[col_ptr] = receipt
        if (self.created_collections is not registry
                or self._collection_creation_receipts is not receipts
                or sum(1 for item in registry if item is record) != 1
                or col_ptr not in receipts
                or receipts.get(col_ptr) is not receipt):
            raise RuntimeError("COLLECTION_REGISTRATION_UNVERIFIED: post-write ledger state inconsistent")
    except BaseException as reg_exc:
        try:
            matched_indices = [idx for idx, item in enumerate(registry) if item is record]
            if matched_indices:
                if len(matched_indices) != 1:
                    raise RuntimeError(
                        f"Ambiguous registry records ({len(matched_indices)}) matched current registration"
                    )
                removed = registry.pop(matched_indices[0])
                if removed is not record or any(item is record for item in registry):
                    raise RuntimeError("Failed to verify removal of current collection registry record")
            elif registry_appended:
                raise RuntimeError("Current collection registry record missing before undo completion")

            if col_ptr in receipts:
                if receipts.get(col_ptr) is receipt:
                    popped_receipt = receipts.pop(col_ptr)
                    if popped_receipt is not receipt or col_ptr in receipts:
                        raise RuntimeError("Failed to verify removal of current collection creation receipt")
                else:
                    raise RuntimeError("Unexpected receipt state encountered during registration undo")
        except BaseException as undo_exc:
            raise RuntimeError(
                "COLLECTION_REGISTRATION_ROLLBACK_FAILED: "
                f"original={type(reg_exc).__name__}: {reg_exc}; "
                f"rollback={type(undo_exc).__name__}: {undo_exc}"
            ) from undo_exc
        raise
