"""Managed Armature session liveness sweep and pre-sweep session/gate scheduling migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from src.scene_transaction_integrity.layer2 import (
    admission_query as _admission_query,
    identity_helpers as _identity_helpers,
    session_identity as _session_identity,
    session_verification as _session_verification,
)
from src.scene_transaction_integrity.layer2.pending_cleanup_registry import (
    _PENDING_ARM_RIG_CLEANUPS,
)
from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _ISOLATED_FAILED_ARMATURES,
    _MANAGED_ARMATURE_IDENTITIES,
)
from src.scene_transaction_integrity.layer2.tombstone_registry import (
    _ARCHIVED_FAILED_D_TOMBSTONES,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _FailedTransactionClass,
)

if TYPE_CHECKING:
    import bpy


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: _sweep_dead_managed_armature_identities
# PURPOSE: 扫描受管 Armature Session 存活状态并将死亡或 Condition 7 失效且已隔离的会话升级为 TOMBSTONED_FAILED_D
# REASON: 将涉及生命周期与墓碑裁决的存活扫描协调迁入 Layer 1，复用 Layer 2 原注册表、状态枚举及核验逻辑
def _sweep_dead_managed_armature_identities(
    *,
    managed_armature_identities: Optional[Dict[str, Any]] = None,
    isolated_failed_armatures: Optional[Dict[str, Any]] = None,
    armature_isolation_state_cls: Any = _ArmatureIsolationState,
    failed_transaction_class_cls: Any = _FailedTransactionClass,
    check_original_object_liveness: Optional[Callable[[Any], Dict[str, Any]]] = None,
    verify_armature_session_identity_record: Optional[Callable[..., Dict[str, Any]]] = None,
) -> None:
    """Refresh liveness of all registered ArmatureSessionIdentityRecords and escalate dead isolated armatures."""
    if managed_armature_identities is None:
        managed_armature_identities = _MANAGED_ARMATURE_IDENTITIES
    if isolated_failed_armatures is None:
        isolated_failed_armatures = _ISOLATED_FAILED_ARMATURES
    if check_original_object_liveness is None:
        check_original_object_liveness = _identity_helpers._check_original_object_liveness
    if verify_armature_session_identity_record is None:
        verify_armature_session_identity_record = (
            _session_verification._verify_armature_session_identity_record
        )
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


# [INTRODUCED 2026-11-25T20:39:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: ensure_armature_session_identity
# PURPOSE: 在解析或注册 Armature 会话身份前执行 Layer 1 前置存活扫描，再委托 Layer 2 完成会话身份解析与注册
# REASON: 将原滞留在 arm_ik.py 中的跨层前置存活扫描调度迁入 Layer 1，消除 Layer 2 反向调用风险与 Arm IK 事务调度职责
def ensure_armature_session_identity(
    arm: bpy.types.Object,
) -> ArmatureSessionIdentityRecord:
    """Layer 1 scheduled entrypoint: sweep dead managed identities before Layer 2 session resolution."""
    _sweep_dead_managed_armature_identities()
    return _session_identity.ensure_armature_session_identity(arm)


# [INTRODUCED 2026-11-25T20:39:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: query_admission_gate_status
# PURPOSE: 在查询准入门禁状态前执行 Layer 1 前置存活扫描，再委托 Layer 2 完成只读准入门禁状态查询
# REASON: 将原滞留在 arm_ik.py 中的跨层前置存活扫描调度迁入 Layer 1，保持原始调用顺序、异常传播与返回结构不变
def query_admission_gate_status(
    arm: Optional[bpy.types.Object] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Layer 1 scheduled entrypoint: sweep dead managed identities before Layer 2 admission gate status query."""
    _sweep_dead_managed_armature_identities()
    return _admission_query.query_admission_gate_status(
        arm,
        session_id,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        archived_failed_d_tombstones=_ARCHIVED_FAILED_D_TOMBSTONES,
        armature_liveness_status_cls=_ArmatureLivenessStatus,
        armature_isolation_state_cls=_ArmatureIsolationState,
        safe_object_pointer=_identity_helpers._safe_object_pointer,
        verify_armature_session_identity_record=(
            _session_verification._verify_armature_session_identity_record
        ),
    )
