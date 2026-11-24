"""Complete Arm Rig transaction coordinator entrypoint migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-09)."""

from typing import Any, Callable, Generator, List, Optional

from src.scene_transaction_integrity.layer1.admission_helpers import (
    _assert_nested_transaction_admission,
    _identity_failure_is_uncertain,
    _safe_object_name,
)
from src.scene_transaction_integrity.layer1.outermost_admission import (
    _admit_outermost_arm_rig_transaction,
    _assert_admission_identity_valid,
)
from src.scene_transaction_integrity.layer1.transaction_establishment import (
    _establish_outermost_arm_rig_transaction,
    _capture_transaction_entry_fingerprint,
    _snapshot_and_activate_transaction,
)
from src.scene_transaction_integrity.layer1.transaction_commit import (
    _commit_arm_rig_transaction,
    _release_active_arm_rig_transaction,
)
from src.scene_transaction_integrity.layer1.post_commit_cleanup import (
    _dispatch_initial_post_commit_cleanup,
)


# [INTRODUCED 2026-11-24T20:58:00+08:00]
# NODE: 10-B / L1-09
# FUNCTION: _arm_rig_transaction
# PURPOSE: 持有完整事务生命周期调度及原异常传播控制流
# REASON: 将事务总入口实际控制权归入 Layer 1，保留兼容入口和既有下游实现
def _arm_rig_transaction(
    arm: Any,
    *,
    active_transaction_stack: List[Any],
    transaction_context_cls: Any,
    transaction_state_cls: Any,
    failed_transaction_class_cls: Any,
    relationship_operation_state_cls: Any,
    ensure_armature_session_identity: Callable[..., Any],
    assert_arm_rig_cleanup_gate: Callable[..., None],
    assert_arm_rig_failed_isolation_gate: Callable[..., None],
    verify_armature_session_identity_record: Callable[..., Any],
    record_armature_failure_isolation_by_coordinator: Callable[..., Any],
    trigger_fault_injection: Callable[..., None],
    capture_pre_snapshot_structural_fingerprint: Callable[..., Any],
    snapshot_arm_rig_state: Callable[..., Any],
    depsgraph_update: Callable[..., None],
    rollback_arm_rig_state: Callable[..., Any],
    verify_arm_rig_state_restored: Callable[..., Any],
    verify_pre_write_zero_mutation_and_integrity: Callable[..., Any],
    coordinator_validate_cleanup_preflight: Callable[..., None],
    coordinator_preserve_cleanup_pending: Callable[..., None],
    coordinator_apply_cleanup_result: Callable[..., None],
) -> Generator[Any, None, None]:
    """Context manager executing Arm IK mutations under atomic transaction protection."""
    if active_transaction_stack:
        outer_tx = active_transaction_stack[-1]
        _assert_nested_transaction_admission(
            arm,
            outer_tx,
            transaction_state_cls=transaction_state_cls,
            safe_object_name=_safe_object_name,
        )
        # Re-entrant invocation on same armature: outer transaction retains exclusive ownership
        try:
            yield outer_tx
        except BaseException as nested_exc:
            outer_tx.mark_rollback_only(f"{type(nested_exc).__name__}: {nested_exc}")
            raise
        return

    # -----------------------------------------------------------------
    # Unified Admission Gate (Section 7):
    # 1. Cleanup Pending Gate -> 2. FAILED Isolation Gate -> 3. Armature Identity Check
    # -----------------------------------------------------------------
    session_rec, admission_id_check = (
        _admit_outermost_arm_rig_transaction(
            arm,
            ensure_armature_session_identity=ensure_armature_session_identity,
            assert_arm_rig_cleanup_gate=assert_arm_rig_cleanup_gate,
            assert_arm_rig_failed_isolation_gate=assert_arm_rig_failed_isolation_gate,
            verify_armature_session_identity_record=verify_armature_session_identity_record,
        )
    )
    _assert_admission_identity_valid(
        arm,
        session_rec,
        admission_id_check,
        identity_failure_is_uncertain=_identity_failure_is_uncertain,
        transaction_context_cls=transaction_context_cls,
        transaction_state_cls=transaction_state_cls,
        failed_transaction_class_cls=failed_transaction_class_cls,
        record_armature_failure_isolation_by_coordinator=(
            record_armature_failure_isolation_by_coordinator
        ),
    )

    tx = _establish_outermost_arm_rig_transaction(
        arm,
        session_rec,
        transaction_context_cls=transaction_context_cls,
        active_transaction_stack=active_transaction_stack,
    )
    pre_snap_fp = None

    try:
        pre_snap_fp = _capture_transaction_entry_fingerprint(
            arm,
            tx,
            trigger_fault_injection=trigger_fault_injection,
            capture_pre_snapshot_structural_fingerprint=(
                capture_pre_snapshot_structural_fingerprint
            ),
        )

        _snapshot_and_activate_transaction(
            arm,
            tx,
            pre_snap_fp,
            transaction_state_cls=transaction_state_cls,
            snapshot_arm_rig_state=snapshot_arm_rig_state,
        )

        yield tx

        _commit_arm_rig_transaction(
            arm,
            tx,
            session_rec,
            transaction_state_cls=transaction_state_cls,
            trigger_fault_injection=trigger_fault_injection,
            depsgraph_update=depsgraph_update,
            verify_armature_session_identity_record=(
                verify_armature_session_identity_record
            ),
        )

    except BaseException as orig_exc:
        # If failure occurred before Phase 2 (Logical Commit), execute classification & rollback!
        if tx.state != transaction_state_cls.COMMITTED:
            if tx.snapshot is not None:
                tx.state = transaction_state_cls.ROLLING_BACK
                rollback_err: Optional[BaseException] = None
                pre_rb_id = verify_armature_session_identity_record(session_rec, candidate_arm=arm)

                if not pre_rb_id["is_valid"]:
                    # An unverified identity is not a proven-dead Armature.
                    # Never roll back through an uncertain or substituted RNA reference.
                    uncertain = _identity_failure_is_uncertain(pre_rb_id)
                    tx.state = transaction_state_cls.FAILED
                    rollback_err = RuntimeError(
                        "Armature session identity invalidated before rollback "
                        f"(registry_session_id={session_rec.registry_session_id}): "
                        + "; ".join(pre_rb_id["reasons"])
                    )
                    record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=(failed_transaction_class_cls.FAILED_C if uncertain
                                       else failed_transaction_class_cls.FAILED_D),
                        primary_exception=orig_exc,
                        secondary_exception=rollback_err,
                        evidence_status=("ARMATURE_IDENTITY_UNVERIFIED_BEFORE_ROLLBACK" if uncertain
                                         else "ARMATURE_DESTROYED_DURING_TRANSACTION"),
                        missing_evidence_reasons=pre_rb_id["reasons"],
                    )
                else:
                    rollback_execution_completed = False
                    try:
                        rollback_arm_rig_state(arm, tx.snapshot, tx)
                        depsgraph_update()
                        rollback_execution_completed = True
                        trigger_fault_injection("during_rollback_verification", {"arm": arm, "tx": tx})
                        verify_arm_rig_state_restored(arm, tx.snapshot, active_tx=tx)
                        tx.state = transaction_state_cls.ROLLED_BACK
                        session_rec.lifecycle_stage = "NORMAL_TERMINAL"
                    except BaseException as rb_exc:
                        tx.state = transaction_state_cls.FAILED
                        rollback_err = rb_exc
                        post_rb_id = verify_armature_session_identity_record(session_rec, candidate_arm=arm)
                        if not post_rb_id["is_valid"]:
                            uncertain = _identity_failure_is_uncertain(post_rb_id)
                            f_class = (failed_transaction_class_cls.FAILED_C if uncertain
                                       else failed_transaction_class_cls.FAILED_D)
                            ev_status = ("ARMATURE_IDENTITY_UNVERIFIED_DURING_ROLLBACK" if uncertain
                                         else "ARMATURE_DESTROYED_DURING_ROLLBACK")
                            ev_reasons = post_rb_id["reasons"]
                        # [INTRODUCED 2026-11-11T22:38:48+08:00]
                        # FUNCTION: _arm_rig_transaction
                        # PURPOSE: Propagate RECOVERY_UNCERTAIN evidence or classify FAILED-C from verified relationship state
                        # REASON: Task 10-B fix-2, TEST-127 / TEST-149
                        elif any(
                            r.get("operation_state") == relationship_operation_state_cls.RECOVERY_UNCERTAIN
                            for r in getattr(tx, "prepared_relationship_mutations", [])
                        ):
                            f_class = failed_transaction_class_cls.FAILED_C
                            ev_status = "SNAPSHOT_AVAILABLE"
                            ev_reasons = []
                        elif not rollback_execution_completed:
                            f_class = failed_transaction_class_cls.FAILED_B
                            ev_status = "SNAPSHOT_AVAILABLE"
                            ev_reasons = []
                        else:
                            f_class = failed_transaction_class_cls.FAILED_C
                            ev_status = "SNAPSHOT_AVAILABLE"
                            ev_reasons = []
                        record_armature_failure_isolation_by_coordinator(
                            session_rec=session_rec,
                            tx=tx,
                            failure_class=f_class,
                            primary_exception=orig_exc,
                            secondary_exception=rb_exc,
                            evidence_status=ev_status,
                            missing_evidence_reasons=ev_reasons,
                        )

                if rollback_err is not None:
                    raise RuntimeError(
                        f"Arm rig transaction failed with {type(orig_exc).__name__}: {orig_exc}, "
                        f"AND rollback verification failed with {type(rollback_err).__name__}: {rollback_err}"
                    ) from orig_exc
                else:
                    raise
            else:
                # Pre-ACTIVE failure (during CREATED or SNAPSHOTTING before snapshot completion)
                tx.state = transaction_state_cls.FAILED
                pre_active_id = verify_armature_session_identity_record(session_rec, candidate_arm=arm)
                if not pre_active_id["is_valid"]:
                    uncertain = _identity_failure_is_uncertain(pre_active_id)
                    f_class = (failed_transaction_class_cls.FAILED_C if uncertain
                               else failed_transaction_class_cls.FAILED_D)
                    record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=f_class,
                        primary_exception=orig_exc,
                        evidence_status=("RECOVERY_EVIDENCE_INSUFFICIENT" if uncertain
                                         else "ARMATURE_DESTROYED_DURING_SNAPSHOTTING"),
                        missing_evidence_reasons=pre_active_id["reasons"],
                    )
                    raise RuntimeError(
                        f"Arm rig transaction failed during SNAPSHOTTING with {type(orig_exc).__name__}: {orig_exc}, "
                        f"AND Armature session identity was invalidated ({f_class.value}, "
                        f"registry_session_id={session_rec.registry_session_id})"
                    ) from orig_exc

                integrity_check = verify_pre_write_zero_mutation_and_integrity(
                    arm=arm,
                    pre_fp=pre_snap_fp,
                    tx=tx,
                )
                if integrity_check["is_verified"]:
                    # FAILED-A: Pre-write abort with 100% verified zero mutation and intact structure.
                    # Do NOT isolate the healthy Armature!
                    record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=failed_transaction_class_cls.FAILED_A,
                        primary_exception=orig_exc,
                        evidence_status="PRE_WRITE_ZERO_MUTATION_VERIFIED",
                    )
                    raise
                else:
                    # Insufficient evidence to prove zero mutation without a trusted snapshot ->
                    # escalate and isolate as FAILED-C (Section 5.1 & Section 8.2 Case 2).
                    record_armature_failure_isolation_by_coordinator(
                        session_rec=session_rec,
                        tx=tx,
                        failure_class=failed_transaction_class_cls.FAILED_C,
                        primary_exception=orig_exc,
                        evidence_status="RECOVERY_EVIDENCE_INSUFFICIENT",
                        missing_evidence_reasons=integrity_check["reasons"],
                    )
                    raise RuntimeError(
                        f"Arm rig transaction failed before ACTIVE with {type(orig_exc).__name__}: {orig_exc}, "
                        "AND pre-write zero-mutation verification failed without a trusted snapshot "
                        f"(classified as FAILED-C, registry_session_id={session_rec.registry_session_id}): "
                        + "; ".join(integrity_check["reasons"])
                    ) from orig_exc
        else:
            raise
    finally:
        _release_active_arm_rig_transaction(
            tx,
            active_transaction_stack=active_transaction_stack,
        )

    # -----------------------------------------------------------------
    # Phase 3: Irreversible Resource Cleanup (runs only after logical commit)
    # -----------------------------------------------------------------
    _dispatch_initial_post_commit_cleanup(
        tx,
        transaction_state_cls=transaction_state_cls,
        trigger_fault_injection=trigger_fault_injection,
        coordinator_validate_cleanup_preflight=(
            coordinator_validate_cleanup_preflight
        ),
        coordinator_preserve_cleanup_pending=(
            coordinator_preserve_cleanup_pending
        ),
        coordinator_apply_cleanup_result=(
            coordinator_apply_cleanup_result
        ),
    )
