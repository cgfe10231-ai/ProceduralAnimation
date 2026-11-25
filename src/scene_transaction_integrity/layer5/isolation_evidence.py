"""Isolation de-isolation and dead tombstone retirement evidence verifiers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 5 L1-10)."""

from typing import Any, Callable, Dict, List, Optional

import bpy
from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)


# [INTRODUCED 2026-11-25T14:51:00+08:00]
# NODE: 10-B / L1-10
# FUNCTION: verify_armature_deisolation_evidence
# PURPOSE: 只读核验失败隔离会话的恢复证据与八项前提条件，产出供 Layer 1 Coordinator 裁决的证据报告
# REASON: 将隔离治理主入口及证据验证链整体迁入目标层
def verify_armature_deisolation_evidence(
    arm: Optional[bpy.types.Object] = None,
    session_id: Optional[str] = None,
    *,
    sweep_dead_managed_armature_identities: Callable[..., Any],
    managed_armature_identities: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    archived_failed_d_tombstones: Dict[str, Dict[str, Any]],
    pending_arm_rig_cleanups: Dict[str, Any],
    active_transaction_stack: List[Any],
    armature_liveness_status_cls: Any,
    armature_isolation_state_cls: Any,
    failed_transaction_class_cls: Any,
    relationship_operation_state_cls: Any,
    verify_armature_session_identity_record: Callable[..., Dict[str, Any]],
    verify_arm_rig_state_restored: Callable[..., None],
    find_live_object_by_identity: Callable[..., Any],
    find_live_collection_by_identity: Callable[..., Any],
) -> Dict[str, Any]:
    """Layer 5: Read-only verification of recovery evidence before de-isolating an Armature (Section 8.2)."""
    sweep_dead_managed_armature_identities()

    session_rec: Optional[ArmatureSessionIdentityRecord] = None
    if session_id is not None:
        session_rec = managed_armature_identities.get(session_id)
    elif arm is not None:
        for rec in managed_armature_identities.values():
            if rec.original_blender_ref is arm:
                session_rec = rec
                break
            if rec.liveness_status == armature_liveness_status_cls.ALIVE_VERIFIED:
                ver = verify_armature_session_identity_record(rec, candidate_arm=arm)
                if ver["is_valid"]:
                    session_rec = rec
                    break

    resolved_session_id = session_rec.registry_session_id if session_rec is not None else session_id
    iso_rec = isolated_failed_armatures.get(resolved_session_id) if resolved_session_id else None
    archived_rec = archived_failed_d_tombstones.get(resolved_session_id) if resolved_session_id else None

    if session_rec is None or (iso_rec is None and archived_rec is None):
        return {
            "can_deisolate": False,
            "status": "NOT_ISOLATED",
            "case": "NONE",
            "registry_session_id": resolved_session_id,
            "failure_class": None,
            "isolation_state": (session_rec.isolation_state.value if session_rec is not None else None),
            "reasons": ["Armature session is not present in _ISOLATED_FAILED_ARMATURES"],
        }

    if archived_rec is not None or session_rec.isolation_state == armature_isolation_state_cls.ARCHIVED_RETIRED:
        return {
            "can_deisolate": False,
            "status": "REJECTED_ARCHIVED_TOMBSTONE",
            "case": "CASE_3_DEAD_TOMBSTONE",
            "registry_session_id": resolved_session_id,
            "failure_class": failed_transaction_class_cls.FAILED_D.value,
            "isolation_state": armature_isolation_state_cls.ARCHIVED_RETIRED.value,
            "reasons": ["FAILED-D tombstone is already ARCHIVED_RETIRED and cannot return to active status"],
        }

    failure_class = iso_rec.get("failure_class")
    target_arm = arm if arm is not None else session_rec.original_blender_ref
    id_ver = verify_armature_session_identity_record(session_rec, candidate_arm=target_arm)

    # Case 3: FAILED-D or dead Armature tombstone
    if (
        failure_class == failed_transaction_class_cls.FAILED_D.value
        or session_rec.isolation_state == armature_isolation_state_cls.TOMBSTONED_FAILED_D
        or session_rec.liveness_status == armature_liveness_status_cls.INVALIDATED_DEAD
    ):
        reasons = [
            "FAILED-D dead Armature tombstone cannot be restored to active status; "
            "use retire_dead_armature_tombstone after verifying residual resources"
        ]
        if not id_ver["is_valid"]:
            reasons.extend(id_ver["reasons"])
        return {
            "can_deisolate": False,
            "status": "REJECTED_DEAD_ARMATURE_TOMBSTONE",
            "case": "CASE_3_DEAD_TOMBSTONE",
            "registry_session_id": resolved_session_id,
            "failure_class": failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "reasons": reasons,
        }

    # Case 2: No trusted pre-transaction snapshot available
    snapshot = iso_rec.get("snapshot_reference")
    snapshot_trusted = bool(iso_rec.get("snapshot_trusted", False) and snapshot is not None)
    if not snapshot_trusted:
        missing_reasons = list(
            iso_rec.get("missing_evidence_reasons")
            or ["Trusted pre-transaction snapshot is missing; recovery evidence is insufficient"]
        )
        return {
            "can_deisolate": False,
            "status": "RECOVERY_EVIDENCE_INSUFFICIENT",
            "case": "CASE_2_NO_TRUSTED_SNAPSHOT",
            "registry_session_id": resolved_session_id,
            "failure_class": failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "reasons": missing_reasons,
        }

    # Case 1: Trusted snapshot exists -> verify all 8 mandatory conditions simultaneously
    reasons: List[str] = []

    # Condition 1: 7-condition ArmatureSessionIdentityRecord verification
    if not id_ver["is_valid"]:
        reasons.extend(id_ver["reasons"])

    # Condition 7 (checked before snapshot restore call because _verify_arm_rig_state_restored also checks stack):
    # _ACTIVE_TRANSACTION_STACK is empty
    if len(active_transaction_stack) != 0:
        reasons.append(
            f"Active transaction stack is not empty (contains {len(active_transaction_stack)} active transaction(s))"
        )

    # Condition 2: Current Armature, Controllers, PoseBones, Constraints, and Collections match snapshot 100%
    if id_ver["is_valid"] and target_arm is not None:
        try:
            verify_arm_rig_state_restored(target_arm, snapshot, active_tx=None)
        except BaseException as ver_exc:
            reasons.append(f"Snapshot state verification failed: {ver_exc}")

    # Condition 3: No transaction-created Controllers remain in bpy.data.objects by identity
    for ctrl_rec in iso_rec.get("created_controller_objects", []):
        c_ref = ctrl_rec.get("obj_ref")
        c_ptr = ctrl_rec.get("obj_ptr")
        c_name = ctrl_rec.get("created_name", "<unknown>")
        if c_ptr is not None and find_live_object_by_identity(c_ref, c_ptr) is not None:
            reasons.append(f"Transaction-created controller '{c_name}' (ptr={c_ptr}) still exists in bpy.data.objects")

    # Condition 4: No transaction-created Constraints remain on any PoseBone by identity
    if id_ver["is_valid"] and target_arm is not None and getattr(target_arm, "pose", None) is not None:
        for con_rec in iso_rec.get("created_constraints", []):
            b_name = con_rec.get("bone_name")
            con_ptr = con_rec.get("con_ptr")
            con_name = con_rec.get("created_name", "<unknown>")
            pbone = target_arm.pose.bones.get(b_name) if b_name else None
            if pbone is not None and con_ptr is not None:
                for live_con in pbone.constraints:
                    try:
                        if live_con.as_pointer() == con_ptr:
                            reasons.append(
                                f"Transaction-created constraint '{con_name}' (ptr={con_ptr}) still exists on bone '{b_name}'"
                            )
                            break
                    except ReferenceError:
                        continue

    # Condition 5: No transaction-created Collections remain in bpy.data.collections by identity
    for col_rec in iso_rec.get("created_collections", []):
        col_ref = col_rec.get("col_ref")
        col_ptr = col_rec.get("col_ptr")
        col_name = col_rec.get("created_name", "<unknown>")
        if find_live_collection_by_identity(col_ref, col_ptr) is not None:
            reasons.append(
                f"Transaction-created collection '{col_name}' (ptr={col_ptr}) still exists in bpy.data.collections"
            )

    # Condition 6: Relationship operation log contains no unverified RECOVERY_UNCERTAIN residual relationships
    for op_rec in iso_rec.get("prepared_relationship_mutations", []):
        op_id = op_rec.get("operation_id", "<unknown>")
        op_state = op_rec.get("operation_state")
        if op_state == relationship_operation_state_cls.RECOVERY_UNCERTAIN:
            reasons.append(
                f"Relationship operation '{op_id}' remains in unverified RECOVERY_UNCERTAIN state"
            )
        elif op_state not in (
            relationship_operation_state_cls.NO_EFFECT,
            relationship_operation_state_cls.REVERTED,
        ):
            reasons.append(
                f"Relationship operation '{op_id}' is in non-terminal rollback state '{op_state}'"
            )

    # Condition 8: No unresolved CLEANUP_PENDING records for this Armature
    pending_cleanups = [
        c_tx_id
        for c_tx_id, c_tx in pending_arm_rig_cleanups.items()
        if c_tx.arm_ptr == session_rec.registration_pointer
        or getattr(c_tx, "session_id", None) == resolved_session_id
    ]
    if pending_cleanups:
        reasons.append(
            f"Unresolved CLEANUP_PENDING transaction(s) exist for this Armature: {sorted(pending_cleanups)}"
        )

    can_deisolate = len(reasons) == 0
    return {
        "can_deisolate": can_deisolate,
        "status": "RECOVERY_VERIFIED" if can_deisolate else "RECOVERY_VERIFICATION_FAILED",
        "case": "CASE_1_SNAPSHOT_VERIFIED",
        "registry_session_id": resolved_session_id,
        "transaction_id": iso_rec.get("transaction_id"),
        "failure_class": failure_class,
        "isolation_state": session_rec.isolation_state.value,
        "reasons": reasons,
    }


# [INTRODUCED 2026-11-25T14:51:00+08:00]
# NODE: 10-B / L1-10
# FUNCTION: _verify_dead_armature_tombstone_retirement_evidence
# PURPOSE: 只读核验 FAILED-D 死亡骨架墓碑退休的存活缺失、残留资源、待清理队列与活动栈四项证据条件
# REASON: 将隔离治理主入口及证据验证链整体迁入目标层
def _verify_dead_armature_tombstone_retirement_evidence(
    session_id: str,
    *,
    sweep_dead_managed_armature_identities: Callable[..., Any],
    managed_armature_identities: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    failed_transaction_class_cls: Any,
    armature_isolation_state_cls: Any,
    check_original_object_liveness: Callable[..., Dict[str, Any]],
    find_live_object_by_identity: Callable[..., Any],
    find_live_collection_by_identity: Callable[..., Any],
    pending_arm_rig_cleanups: Dict[str, Any],
    active_transaction_stack: List[Any],
) -> Dict[str, Any]:
    """Layer 5: Read-only verification of dead Armature tombstone retirement conditions (Section 8.2 Case 3)."""
    sweep_dead_managed_armature_identities()

    session_rec = managed_armature_identities.get(session_id)
    iso_rec = isolated_failed_armatures.get(session_id)

    if session_rec is None or iso_rec is None:
        return {
            "can_retire": False,
            "status": "TOMBSTONE_NOT_FOUND",
            "registry_session_id": session_id,
            "reasons": [f"Active FAILED-D tombstone for session '{session_id}' not found"],
        }

    reasons: List[str] = []

    if (
        iso_rec.get("failure_class") != failed_transaction_class_cls.FAILED_D.value
        or session_rec.isolation_state != armature_isolation_state_cls.TOMBSTONED_FAILED_D
    ):
        reasons.append(
            f"Session '{session_id}' is not a FAILED-D tombstone "
            f"(failure_class={iso_rec.get('failure_class')}, isolation_state={session_rec.isolation_state})"
        )

    # 1. Confirm original Armature is genuinely absent from live Blender objects
    # (Never mistake a same-name replacement Armature for the original,
    # and NEVER mistake data invalidation on an existing Armature for object death)
    obj_liveness = check_original_object_liveness(session_rec)
    if obj_liveness["status"] != "ABSENT":
        if obj_liveness["status"] == "UNKNOWN":
            reasons.append(
                f"OBJECT_EXISTENCE_UNVERIFIED: Cannot verify absence of original Armature "
                f"(ptr={session_rec.registration_pointer}, status=UNKNOWN); cannot retire tombstone"
            )
        else:
            reasons.append(
                f"Original Armature object still exists in bpy.data.objects (ptr={session_rec.registration_pointer}); "
                "cannot retire tombstone"
            )
    elif session_rec.in_live_blender_collection:
        reasons.append(
            f"Original Armature object still marked as present in live collection (ptr={session_rec.registration_pointer}); "
            "cannot retire tombstone"
        )

    # 2. Confirm no transaction-created objects or collections from the failed transaction remain in bpy.data
    for ctrl_rec in iso_rec.get("created_controller_objects", []):
        c_ref = ctrl_rec.get("obj_ref")
        c_ptr = ctrl_rec.get("obj_ptr")
        c_name = ctrl_rec.get("created_name", "<unknown>")
        if c_ptr is not None and find_live_object_by_identity(c_ref, c_ptr) is not None:
            reasons.append(
                f"Residual transaction-created controller '{c_name}' (ptr={c_ptr}) still exists in bpy.data.objects"
            )

    for col_rec in iso_rec.get("created_collections", []):
        col_ref = col_rec.get("col_ref")
        col_ptr = col_rec.get("col_ptr")
        col_name = col_rec.get("created_name", "<unknown>")
        if find_live_collection_by_identity(col_ref, col_ptr) is not None:
            reasons.append(
                f"Residual transaction-created collection '{col_name}' (ptr={col_ptr}) still exists in bpy.data.collections"
            )

    # 3. Confirm no unresolved CLEANUP_PENDING records remain for this session
    pending_cleanups = [
        c_tx_id
        for c_tx_id, c_tx in pending_arm_rig_cleanups.items()
        if getattr(c_tx, "session_id", None) == session_id
        or c_tx.arm_ptr == session_rec.registration_pointer
    ]
    if pending_cleanups:
        reasons.append(
            f"Unresolved CLEANUP_PENDING transaction(s) remain for dead Armature session: {sorted(pending_cleanups)}"
        )

    # 4. Confirm _ACTIVE_TRANSACTION_STACK is empty
    if len(active_transaction_stack) != 0:
        reasons.append("Active transaction stack is not empty")

    can_retire = len(reasons) == 0
    return {
        "can_retire": can_retire,
        "status": "TOMBSTONE_RETIREMENT_VERIFIED" if can_retire else "TOMBSTONE_RETIREMENT_REJECTED",
        "registry_session_id": session_id,
        "transaction_id": iso_rec.get("transaction_id"),
        "failure_class": iso_rec.get("failure_class"),
        "isolation_state": session_rec.isolation_state.value,
        "reasons": reasons,
    }