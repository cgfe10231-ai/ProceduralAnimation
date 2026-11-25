"""FAILED isolation controller recovery authority verification migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-10)."""

from typing import Any, Callable, Dict, Optional

import bpy


# [INTRODUCED 2026-11-25T15:59:57+08:00]
# NODE: 10-B / L3-10
# FUNCTION: _verify_failed_isolation_controller_recovery_authority
# PURPOSE: 在回滚期间核验 FAILED-B/C 隔离事务对原始 Controller 恢复操作的完整受权证据链并严格拒绝 FAILED-D
# REASON: 将 FAILED 隔离 Controller 恢复权限验证从 arm_ik.py 物理迁入 Layer 3，全部依赖经显式参数传入
def _verify_failed_isolation_controller_recovery_authority(
    arm: bpy.types.Object,
    obj: bpy.types.Object,
    snapshot: Dict[str, Any],
    tx: Any,
    expected_role: Optional[tuple[str, str]],
    *,
    transaction_context_cls: Any,
    transaction_state_cls: Any,
    managed_armature_identities: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    failed_transaction_class_cls: Any,
    armature_isolation_state_cls: Any,
    armature_liveness_status_cls: Any,
    verify_armature_session_identity_record: Callable[..., Dict[str, Any]],
    find_live_object_by_identity: Callable[..., Optional[bpy.types.Object]],
    controller_role_for_name: Callable[[str], Optional[tuple[str, str]]],
    controller_constraint_binding_proven: Callable[..., bool],
    controller_is_borrowed_by_other_armature: Callable[..., bool],
) -> tuple[bool, str]:
    """Verify that a FAILED-isolated transaction holds legal authority to restore original Controller state.

    Must verify all 8 conditions from Task 10-B dynamic acceptance requirements:
    1. Armature identity and liveness
    2. Session identity and isolation registration
    3. Transaction identity and context binding
    4. Snapshot reference and trustworthiness consistency
    5. Controller original reference, pointer, and non-creation baseline
    6. Original IK constraint binding provenance
    7. Absence of borrowing by any foreign Armature
    8. FAILED isolation class (FAILED-B or FAILED-C only; FAILED-D strictly denied)
    """
    if not isinstance(tx, transaction_context_cls):
        return False, "Transaction is not an _ArmRigTransactionContext instance"

    if tx.state != transaction_state_cls.FAILED:
        return False, f"Transaction state is {tx.state!r}, expected FAILED"

    # 1. Armature identity
    if arm is None or not isinstance(arm, bpy.types.Object) or arm.type != "ARMATURE":
        return False, "Armature object is missing or invalid type"
    try:
        arm_ptr = int(arm.as_pointer())
        if arm_ptr <= 0 or tx.arm is not arm or tx.arm_ptr != arm_ptr:
            return False, "Armature reference/pointer does not match transaction"
    except (AttributeError, ReferenceError, TypeError, ValueError) as exc:
        return False, f"Armature pointer access error: {exc}"

    # 2. Session identity
    session_id = getattr(tx, "session_id", None)
    if not isinstance(session_id, str) or not session_id:
        return False, "Transaction session_id is missing or empty"

    session_rec = managed_armature_identities.get(session_id)
    if session_rec is None:
        return False, f"Session ID {session_id!r} not found in _MANAGED_ARMATURE_IDENTITIES"
    if tx.session_record is not session_rec or session_rec.registry_session_id != session_id:
        return False, "Session record mismatch with transaction"
    if session_rec.original_blender_ref is not arm or session_rec.registration_pointer != arm_ptr:
        return False, "Session record registration does not match Armature"

    # [INTRODUCED 2026-11-11T19:47:00+08:00]
    # FUNCTION: _verify_failed_isolation_controller_recovery_authority
    # PURPOSE: Enforce strict bidirectional consistency between isolation record, tx context, failure class, and session state
    # REASON: Task 10-B fix-1: complete isolation record consistency validation for TEST-131, 136, 147, 155
    iso_rec = isolated_failed_armatures.get(session_id)
    if not isinstance(iso_rec, dict):
        return False, f"No active isolation record in _ISOLATED_FAILED_ARMATURES for session {session_id!r}"
    if iso_rec.get("registry_session_id") != session_id:
        return False, f"Isolation record registry_session_id {iso_rec.get('registry_session_id')!r} != session_id {session_id!r}"
    if iso_rec.get("transaction_id") != tx.tx_id:
        return False, f"Isolation record transaction_id {iso_rec.get('transaction_id')!r} != tx.tx_id {tx.tx_id!r}"
    tx_ctx = iso_rec.get("transaction_context")
    if tx_ctx is None or tx_ctx is not tx:
        return False, "Isolation record transaction_context is missing, None, or does not match active tx"

    failure_class = iso_rec.get("failure_class")
    if failure_class in (failed_transaction_class_cls.FAILED_D.value, "FAILED-D"):
        return False, "FAILED-D tombstones are strictly denied controller recovery authority"
    if failure_class not in (
        failed_transaction_class_cls.FAILED_B.value,
        failed_transaction_class_cls.FAILED_C.value,
        "FAILED-B",
        "FAILED-C",
    ):
        return False, f"Unsupported failure class for recovery: {failure_class!r}"

    tx_failure_class = getattr(tx, "failure_class", None)
    if failure_class != tx_failure_class:
        return False, f"Isolation record failure_class {failure_class!r} != tx.failure_class {tx_failure_class!r}"

    iso_state = session_rec.isolation_state
    if iso_state in (
        armature_isolation_state_cls.TOMBSTONED_FAILED_D,
        armature_isolation_state_cls.ARCHIVED_RETIRED,
        armature_isolation_state_cls.NONE,
    ):
        return False, f"Armature session isolation state {iso_state!r} is not an active FAILED isolation"

    if failure_class in (failed_transaction_class_cls.FAILED_B.value, "FAILED-B"):
        if iso_state != armature_isolation_state_cls.ISOLATED_FAILED_B:
            return False, f"Failure class FAILED-B requires isolation_state ISOLATED_FAILED_B, got {iso_state!r}"
    elif failure_class in (failed_transaction_class_cls.FAILED_C.value, "FAILED-C"):
        if iso_state != armature_isolation_state_cls.ISOLATED_FAILED_C:
            return False, f"Failure class FAILED-C requires isolation_state ISOLATED_FAILED_C, got {iso_state!r}"

    rec_iso_state_val = iso_state.value if hasattr(iso_state, "value") else str(iso_state)
    if iso_rec.get("isolation_state") != rec_iso_state_val:
        return False, f"Isolation record isolation_state {iso_rec.get('isolation_state')!r} != session_rec.isolation_state {rec_iso_state_val!r}"

    if session_rec.liveness_status == armature_liveness_status_cls.INVALIDATED_DEAD:
        return False, "Armature is marked INVALIDATED_DEAD"

    id_ver = verify_armature_session_identity_record(session_rec, candidate_arm=arm)
    if not id_ver.get("is_valid", False):
        return False, f"Armature session identity record is invalid: {'; '.join(id_ver.get('reasons', []))}"

    # 4. Snapshot reference and trustworthiness consistency
    if not isinstance(snapshot, dict):
        return False, "Snapshot is not a valid dictionary"

    trusted_snap = iso_rec.get("snapshot_reference")
    if not iso_rec.get("snapshot_trusted", False) or trusted_snap is None:
        return False, "Isolation record indicates snapshot is not trusted or missing"
    if iso_rec.get("evidence_status") == "RECOVERY_EVIDENCE_INSUFFICIENT":
        return False, "Isolation record evidence_status is RECOVERY_EVIDENCE_INSUFFICIENT"
    if trusted_snap is not snapshot or tx.snapshot is not snapshot:
        return False, "Snapshot reference does not match trusted isolation snapshot or tx.snapshot"

    # 5. Controller original reference, pointer, and baseline
    if obj is None or not isinstance(obj, bpy.types.Object) or obj.type != "EMPTY":
        return False, "Controller object is missing or not an EMPTY"
    try:
        obj_ptr = int(obj.as_pointer())
        if obj_ptr <= 0 or find_live_object_by_identity(obj, obj_ptr) is None:
            return False, "Controller object is not live or cannot be identified"
    except (AttributeError, ReferenceError, TypeError, ValueError) as exc:
        return False, f"Controller pointer access error: {exc}"

    if not isinstance(tx.entry_object_ptrs, (frozenset, set)):
        return False, "Transaction entry_object_ptrs baseline is missing"
    if obj_ptr not in tx.entry_object_ptrs:
        return False, f"Controller ptr={obj_ptr} was not present in transaction entry_object_ptrs baseline"

    created_regs = [
        r for r in getattr(tx, "created_controller_objects", [])
        if isinstance(r, dict) and r.get("obj_ptr") == obj_ptr
    ]
    if created_regs:
        return False, f"Controller ptr={obj_ptr} is recorded as transaction-created; not an original controller"

    saved = None
    saved_name = None
    for orig_name, orig_rec in snapshot.get("controllers", {}).items():
        if isinstance(orig_rec, dict) and orig_rec.get("obj_ptr") == obj_ptr and orig_rec.get("obj_ref") == obj:
            if saved is not None:
                return False, f"Multiple snapshot controllers match ptr={obj_ptr}"
            saved = orig_rec
            saved_name = orig_name

    if saved is None:
        return False, f"Controller ptr={obj_ptr} has no matching entry in trusted snapshot"
    if not saved.get("exists", False) or saved.get("type") != "EMPTY":
        return False, f"Snapshot controller record for ptr={obj_ptr} is not a valid pre-existing EMPTY"

    role = controller_role_for_name(saved_name)
    if role is None:
        return False, f"Cannot determine controller role for snapshot name {saved_name!r}"
    if expected_role is not None and role != expected_role:
        return False, f"Controller role {role!r} does not match expected role {expected_role!r}"

    # 6. Original IK constraint binding provenance
    if not controller_constraint_binding_proven(arm, obj, role, snapshot):
        return False, f"Controller binding to IK constraint on role {role!r} cannot be proven from snapshot"

    # 7. Absence of borrowing by any foreign Armature
    if controller_is_borrowed_by_other_armature(arm, obj, role):
        return False, f"Controller is borrowed by another Armature constraint"

    return True, "AUTHORIZED"
