"""Managed Armature session liveness sweep migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-08)."""

from typing import Any, Callable, Dict


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: _sweep_dead_managed_armature_identities
# PURPOSE: 扫描受管 Armature Session 存活状态并将死亡或 Condition 7 失效且已隔离的会话升级为 TOMBSTONED_FAILED_D
# REASON: 将涉及生命周期与墓碑裁决的存活扫描协调迁入 Layer 1，复用 Layer 2 原注册表、状态枚举及核验逻辑
def _sweep_dead_managed_armature_identities(
    *,
    managed_armature_identities: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Any],
    armature_isolation_state_cls: Any,
    failed_transaction_class_cls: Any,
    check_original_object_liveness: Callable[[Any], Dict[str, Any]],
    verify_armature_session_identity_record: Callable[..., Dict[str, Any]],
) -> None:
    """Refresh liveness of all registered ArmatureSessionIdentityRecords and escalate dead isolated armatures."""
    for session_id, rec in list(managed_armature_identities.items()):
        if rec.isolation_state == armature_isolation_state_cls.ARCHIVED_RETIRED:
            continue
        obj_liveness = check_original_object_liveness(rec)
        if obj_liveness["status"] == "UNKNOWN":
            # Cannot prove death or liveness; preserve existing isolation state without escalation
            continue
        ver = verify_armature_session_identity_record(rec, candidate_arm=None)
        # Only escalate to TOMBSTONED_FAILED_D if object is genuinely ABSENT
        # or if object is ALIVE but data block identity has been invalidated/replaced (Condition 7 failed).
        is_dead = (obj_liveness["status"] == "ABSENT")
        is_data_invalidated = (
            obj_liveness["status"] == "ALIVE"
            and not ver.get("identity_verification_uncertain", False)
            and not ver["checks"].get("c7_data_valid_and_pointer_matches", False)
        )
        if is_dead or is_data_invalidated:
            iso_rec = isolated_failed_armatures.get(session_id)
            if iso_rec is not None and rec.isolation_state != armature_isolation_state_cls.TOMBSTONED_FAILED_D:
                rec.isolation_state = armature_isolation_state_cls.TOMBSTONED_FAILED_D
                rec.lifecycle_stage = "TOMBSTONED_FAILED_D"
                tombstone = {
                    "registry_session_id": session_id,
                    "registration_pointer": rec.registration_pointer,
                    "original_data_pointer": rec.original_data_pointer,
                    "registered_name_snapshot": rec.registered_name_snapshot,
                    "failure_class": failed_transaction_class_cls.FAILED_D.value,
                    "isolation_state": armature_isolation_state_cls.TOMBSTONED_FAILED_D.value,
                    "retirement_state": "ACTIVE_TOMBSTONE",
                    "reasons": ver["reasons"],
                }
                rec.tombstone_record = tombstone
                iso_rec["failure_class"] = failed_transaction_class_cls.FAILED_D.value
                iso_rec["isolation_state"] = armature_isolation_state_cls.TOMBSTONED_FAILED_D.value
                iso_rec["tombstone_record"] = tombstone
