"""Controller ownership verification and admission migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-02)."""

from typing import Any, Callable, Dict, List, Optional

import bpy

from src.rig.arm_ik import (
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _MANAGED_ARMATURE_IDENTITIES,
)
from src.scene_transaction_integrity.layer2.transaction_context import (
    _ArmRigTransactionContext,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)
from src.scene_transaction_integrity.layer3.resource_contracts import (
    ExternalControllerNameConflictError,
    _controller_constraint_binding_proven,
    _find_live_object_by_identity,
)


def _controller_role_for_name(
    name: str,
    *,
    arm_ik_target_names: Dict[str, str] = ARM_IK_TARGET_NAMES,
    arm_pole_target_names: Dict[str, str] = ARM_POLE_TARGET_NAMES,
) -> tuple[str, str] | None:
    """Resolve one of four Arm IK roles, never grant authority on its own."""
    for side in ('L', 'R'):
        if name == arm_ik_target_names[side]:
            return (side, 'target')
        if name == arm_pole_target_names[side]:
            return (side, 'pole_target')
    return None


def _controller_is_borrowed_by_other_armature(
    arm: bpy.types.Object,
    obj: bpy.types.Object,
    role: tuple[str, str],
    *,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ] = _find_live_object_by_identity,
) -> bool:
    """Deny a controller referenced by ANY constraint on another Armature.

    Retain the existing role parameter and the original Coordinator-owned
    permission path. Inspect all foreign Armature pose-bone and object
    constraints, not just a same-named IK constraint on forearm.L/R.
    """
    try:
        obj_ptr = int(obj.as_pointer())
        if obj_ptr <= 0 or find_live_object_by_identity(obj, obj_ptr) is None:
            return True
        for other in bpy.data.objects:
            if other == arm or other.type != 'ARMATURE':
                continue
            # Object-level constraints on the foreign Armature may also borrow
            # the controller. A matching target in any pose-bone constraint
            # independently proves that ownership is shared or ambiguous.
            constraints = list(other.constraints)
            if other.pose is not None:
                for bone in other.pose.bones:
                    constraints.extend(bone.constraints)
            for con in constraints:
                for field in ('target', 'pole_target'):
                    bound = getattr(con, field, None)
                    if (bound is not None and bound == obj
                            and int(bound.as_pointer()) == obj_ptr):
                        return True
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
        # A failed inspection cannot certify exclusive controller ownership.
        return True
    return False


def _verify_controller_object_transaction_authority(
    obj: bpy.types.Object,
    tx: Any,
    *,
    created_only: bool = False,
    transaction_context_cls: type = _ArmRigTransactionContext,
    transaction_state_cls: Any = _ArmRigTransactionState,
    managed_armature_identities: Optional[Dict[str, Any]] = None,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ] = _find_live_object_by_identity,
    controller_role_for_name: Callable[[str], tuple[str, str] | None] = _controller_role_for_name,
    controller_constraint_binding_proven: Callable[..., bool] = _controller_constraint_binding_proven,
    controller_is_borrowed_by_other_armature: Callable[
        [bpy.types.Object, bpy.types.Object, tuple[str, str]],
        bool,
    ] = _controller_is_borrowed_by_other_armature,
) -> Optional[str]:
    """Check the existing transaction controller authorization boundary.

    TX_CREATED needs an independently minted registration receipt and absence
    from the entry pointer baseline. SNAPSHOT_ORIGINAL additionally needs a
    real original IK constraint binding, not merely a name-based snapshot.
    """
    if managed_armature_identities is None:
        managed_armature_identities = _MANAGED_ARMATURE_IDENTITIES
    if not isinstance(tx, transaction_context_cls):
        return None
    if tx.state not in (transaction_state_cls.ACTIVE, transaction_state_cls.ROLLING_BACK):
        return None
    if not isinstance(tx.entry_object_ptrs, (frozenset, set)):
        return None
    session_id, record = tx.session_id, tx.session_record
    if not isinstance(session_id, str) or not session_id or record is None:
        return None
    if managed_armature_identities.get(session_id) is not record:
        return None
    if record.registry_session_id != session_id or record.original_blender_ref is not tx.arm:
        return None
    try:
        if int(tx.arm.as_pointer()) != tx.arm_ptr or tx.arm_ptr != record.registration_pointer:
            return None
        ptr = int(obj.as_pointer())
        name = str(obj.name)
        if ptr <= 0 or find_live_object_by_identity(obj, ptr) is None:
            return None
    except (AttributeError, ReferenceError, TypeError, ValueError):
        return None
    role = controller_role_for_name(name)
    # Renaming a controller during a transaction does not erase its creation
    # provenance; it does, however, bar new relationship authorizations by name.
    created_regs = [r for r in tx.created_controller_objects
                    if isinstance(r, dict) and r.get('obj_ptr') == ptr]
    receipts = getattr(tx, '_controller_creation_receipts', None)
    receipt = receipts.get(ptr) if isinstance(receipts, dict) else None
    created = (
        len(created_regs) == 1
        and created_regs[0].get('obj_ref') == obj
        and isinstance(receipt, tuple) and len(receipt) == 4
        and receipt[0] == obj and receipt[1] == session_id
        and receipt[2] == tx.tx_id and receipt[3] is tx._controller_receipt_seal
        and ptr not in tx.entry_object_ptrs
    )
    if created:
        return 'TX_CREATED'
    if created_only or ptr not in tx.entry_object_ptrs or created_regs:
        return None
    snapshot = tx.snapshot
    if not isinstance(snapshot, dict):
        return None
    # Resolve the ORIGINAL name and role by snapshot pointer/reference, so a
    # renamed live object can still be safely restored without trusting its
    # current name or borrowing another same-name replacement.
    saved = None
    for original_name, original_rec in snapshot.get('controllers', {}).items():
        if not isinstance(original_rec, dict):
            continue
        if original_rec.get('obj_ptr') == ptr and original_rec.get('obj_ref') == obj:
            if saved is not None:
                return None
            saved = original_rec
            role = controller_role_for_name(original_name)
    if (role is None or not isinstance(saved, dict)
            or saved.get('exists') is not True
            or saved.get('type') != 'EMPTY' or obj.type != 'EMPTY'):
        return None
    if not controller_constraint_binding_proven(tx.arm, obj, role, snapshot):
        return None
    if controller_is_borrowed_by_other_armature(tx.arm, obj, role):
        return None
    return 'SNAPSHOT_ORIGINAL'


def _require_existing_arm_ik_controller_ownership(
    arm: bpy.types.Object,
    *,
    scope: str,
    active_transaction_stack: Optional[List[Any]] = None,
    arm_ik_target_names: Dict[str, str] = ARM_IK_TARGET_NAMES,
    arm_pole_target_names: Dict[str, str] = ARM_POLE_TARGET_NAMES,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ] = _find_live_object_by_identity,
    verify_controller_object_transaction_authority: Callable[
        ..., Optional[str]
    ] = _verify_controller_object_transaction_authority,
    controller_role_for_name: Callable[[str], tuple[str, str] | None] = _controller_role_for_name,
    controller_constraint_binding_proven: Callable[..., bool] = _controller_constraint_binding_proven,
    controller_is_borrowed_by_other_armature: Callable[
        [bpy.types.Object, bpy.types.Object, tuple[str, str]],
        bool,
    ] = _controller_is_borrowed_by_other_armature,
) -> None:
    """Read-only Arm IK ownership admission; never upgrade an active transaction.

    When a transaction is active, only its entry snapshot proof or its
    transaction-created receipt can authorize a controller. A constraint
    assigned *after* transaction entry cannot retroactively authorize an
    originally unrelated same-name Empty. Outside transactions, established
    live Arm IK bindings remain the backwards-compatible proof of ownership.
    Unbound pre-existing Empties fail closed: their ownership is unknowable.
    """
    if active_transaction_stack is None:
        active_transaction_stack = _ACTIVE_TRANSACTION_STACK
    tx = active_transaction_stack[-1] if active_transaction_stack else None
    for side in ('L', 'R'):
        for name in (arm_ik_target_names[side], arm_pole_target_names[side]):
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            try:
                ptr = int(obj.as_pointer())
                if ptr <= 0 or find_live_object_by_identity(obj, ptr) is None:
                    raise RuntimeError('invalid Blender object identity')
            except (ReferenceError, AttributeError, ValueError, TypeError) as exc:
                raise RuntimeError(f'EXTERNAL_CONTROLLER_NAME_CONFLICT: {scope}: {name} identity unreadable') from exc
            if tx is not None:
                if tx.arm is arm:
                    if verify_controller_object_transaction_authority(obj, tx, created_only=True) == 'TX_CREATED':
                        continue
                    if verify_controller_object_transaction_authority(obj, tx) == 'SNAPSHOT_ORIGINAL':
                        continue
                # Important: no live-binding fallback inside a transaction.
                # Live constraints may have been modified since its snapshot;
                # they do not confer ownership on an entry-time external Empty.
                raise ExternalControllerNameConflictError(
                    f'EXTERNAL_CONTROLLER_NAME_CONFLICT: {scope}: controller {name!r} '
                    'has no proven ownership in the active transaction'
                )
            role = controller_role_for_name(name)
            if (obj.type == 'EMPTY' and role is not None
                    and controller_constraint_binding_proven(arm, obj, role)
                    and not controller_is_borrowed_by_other_armature(arm, obj, role)):
                continue
            raise ExternalControllerNameConflictError(
                f'EXTERNAL_CONTROLLER_NAME_CONFLICT: {scope}: controller {name!r} '
                'is present without a verified owning Armature/transaction binding'
            )


def _verify_transaction_wrong_type_object_ownership(
    obj: bpy.types.Object,
    tx: Optional[Any],
    arm: Optional[bpy.types.Object] = None,
    *,
    transaction_state_cls: Any = _ArmRigTransactionState,
    active_transaction_stack: Optional[List[Any]] = None,
    verify_controller_object_transaction_authority: Callable[
        ..., Optional[str]
    ] = _verify_controller_object_transaction_authority,
) -> bool:
    """Only current transaction-created objects may be replaced by controller name."""
    if active_transaction_stack is None:
        active_transaction_stack = _ACTIVE_TRANSACTION_STACK
    if tx is None or tx.state != transaction_state_cls.ACTIVE:
        return False
    if not active_transaction_stack or active_transaction_stack[-1] is not tx:
        return False
    if arm is not None and tx.arm is not arm:
        return False
    return verify_controller_object_transaction_authority(
        obj, tx, created_only=True,
    ) == 'TX_CREATED'


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: _preflight_wrong_type_controller_conflicts
# PURPOSE: 在进入 setup_arm_ik 事务前预检四名核心控制器的同名非 EMPTY 外部对象冲突
# REASON: 将 Layer 4 内联 Wrong-type 控制器名称冲突预检迁入 Layer 3，保持与已有角色归属核验的原有顺序及独立合同
def _preflight_wrong_type_controller_conflicts(
    arm: bpy.types.Object,
    *,
    active_transaction_stack: List[Any],
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    verify_transaction_wrong_type_object_ownership: Callable[..., bool],
) -> None:
    """Preflight check 4 controller names for external wrong-type conflicts before entering transaction (F14-05 Entrance A)."""
    active_tx = active_transaction_stack[-1] if active_transaction_stack else None
    for c_name in (
        arm_ik_target_names["L"],
        arm_ik_target_names["R"],
        arm_pole_target_names["L"],
        arm_pole_target_names["R"],
    ):
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is not None and c_obj.type != "EMPTY":
            if not verify_transaction_wrong_type_object_ownership(c_obj, active_tx, arm):
                raise ExternalControllerNameConflictError(
                    f"EXTERNAL_CONTROLLER_NAME_CONFLICT: Controller '{c_name}' matches pre-existing or external "
                    f"non-EMPTY object '{c_obj.name}' (type='{c_obj.type}') not owned by active transaction."
                )
