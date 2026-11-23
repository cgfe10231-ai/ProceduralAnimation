"""Controller creation receipt registration migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-07)."""

from typing import Any, Callable, Optional, Tuple

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


# [INTRODUCED 2026-11-23T20:27:30+08:00]
# NODE: 10-B / L2-07
# FUNCTION: _register_created_controller
# PURPOSE: Verify active transaction ownership, session identity, live Blender Object identity, Arm IK controller role, and pre-link/pre-parent preconditions before recording registry entry and sealed 4-tuple receipt in Layer 2
# REASON: Authorized L2-07 migration of _ArmRigTransactionContext.register_created_controller execution body to Layer 2 along the normal asset creation path while preserving original class identity and explicit Layer 3 query callbacks
def _register_created_controller(
    self: Any,
    obj: bpy.types.Object,
    *,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ],
    controller_role_for_name: Callable[[str], Optional[Tuple[str, str]]],
) -> None:
    """Preserve the legacy API; attest an explicit creation in this ACTIVE tx.

    This registration is a trusted explicit transaction operation, not an
    automatically inferred permission from a controller name or a mutable
    created_controller_objects entry alone.
    """
    if self.state != _ArmRigTransactionState.ACTIVE:
        raise RuntimeError('Cannot register created controller outside ACTIVE transaction')
    if not _ACTIVE_TRANSACTION_STACK or _ACTIVE_TRANSACTION_STACK[-1] is not self:
        raise RuntimeError('Created controller registration requires its owning transaction')
    if not isinstance(self.entry_object_ptrs, (frozenset, set)):
        raise RuntimeError('Created controller registration has no trusted entry object baseline')
    if (self.session_record is None
            or _MANAGED_ARMATURE_IDENTITIES.get(self.session_id) is not self.session_record
            or self.session_record.original_blender_ref is not self.arm):
        raise RuntimeError('Created controller registration has no original Armature session identity')
    try:
        obj_ptr = int(obj.as_pointer())
        live = find_live_object_by_identity(obj, obj_ptr)
    except (ReferenceError, AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError('Created controller identity could not be verified') from exc
    if obj_ptr <= 0 or live is None:
        raise RuntimeError('Created controller is not a live Blender Object')
    if obj_ptr in self.entry_object_ptrs:
        raise RuntimeError('Cannot register a pre-existing object as transaction-created')
    # A transaction-created Controller must be registered immediately, before
    # ANY Collection link. An arbitrary scene Object cannot be adopted through
    # the legacy registration API merely because it was created after entry.
    if controller_role_for_name(str(obj.name)) is None:
        raise RuntimeError('Created controller registration requires an Arm IK controller role')
    if obj.users_collection:
        raise RuntimeError('Created controller must be registered before Collection links')
    if obj.parent is not None:
        raise RuntimeError('Created controller must be registered before parent assignment')
    if obj_ptr in self._controller_creation_receipts:
        raise RuntimeError('Duplicate controller creation receipt')
    for registered in self.created_controller_objects:
        if not isinstance(registered, dict) or registered.get('obj_ptr') == obj_ptr:
            raise RuntimeError('Duplicate or malformed transaction controller registration')
    self.created_controller_objects.append({
        'obj_ref': obj, 'obj_ptr': obj_ptr, 'created_name': obj.name,
    })
    # Receipt is independent of the mutable public legacy registry list.
    self._controller_creation_receipts[obj_ptr] = (
        obj, self.session_id, self.tx_id, self._controller_receipt_seal,
    )
