"""Outermost Arm Rig transaction admission coordinator migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-01)."""

from typing import Any, Callable, Dict, Optional, Tuple


# [INTRODUCED 2026-11-24T00:37:30+08:00]
# NODE: 10-B / L1-01
# FUNCTION: _admit_outermost_arm_rig_transaction
# PURPOSE: 按原始顺序协调外层 Arm Rig 事务的 Session 建立、Cleanup Gate、FAILED Gate 和身份验证调用
# REASON: 将正常外层事务准入调用迁入 Layer 1，同时保留原协调器的失败分支和最终事务控制权
def _admit_outermost_arm_rig_transaction(
    arm: Any,
    *,
    ensure_armature_session_identity: Callable[[Any], Any],
    assert_arm_rig_cleanup_gate: Callable[[Any, Any], None],
    assert_arm_rig_failed_isolation_gate: Callable[[Any, Any], None],
    verify_armature_session_identity_record: Callable[..., Dict[str, Any]],
) -> Tuple[Any, Dict[str, Any]]:
    """Execute outermost transaction admission gates and session identity verification in original order."""
    session_rec = ensure_armature_session_identity(arm)

    # Gate 1: Reject a new outermost transaction when previous committed cleanup is unresolved
    assert_arm_rig_cleanup_gate(arm, session_rec)

    # Gate 2: Reject a new outermost transaction when Armature session is isolated due to FAILED
    assert_arm_rig_failed_isolation_gate(arm, session_rec)

    # Gate 3: Verify 7-condition Armature Session Identity
    admission_id_check = verify_armature_session_identity_record(session_rec, candidate_arm=arm)
    return session_rec, admission_id_check


# [INTRODUCED 2026-11-24T13:16:00+08:00]
# NODE: 10-B / L1-03
# FUNCTION: _assert_arm_rig_cleanup_gate
# PURPOSE: 检查待清理注册表中是否存在与当前骨架或会话关联的 CLEANUP_PENDING 事务并阻断新写入
# REASON: 将外层事务 Cleanup Gate 迁入 Layer 1，并复用 Layer 2 单一 Pending Cleanup 注册表与状态枚举
def _assert_arm_rig_cleanup_gate(
    arm: Any,
    session_record: Optional[Any] = None,
    *,
    pending_arm_rig_cleanups: Dict[str, Any],
    safe_object_pointer: Callable[..., int],
    transaction_state_cls: Any,
) -> None:
    """
    Reject new independent writes while the same Armature
    owns an unresolved committed cleanup transaction.
    """

    arm_ptr = safe_object_pointer(
        arm,
        fallback=(session_record.registration_pointer if session_record is not None else 0),
    )
    session_id = session_record.registry_session_id if session_record is not None else None

    blocking_transactions = []

    for tx_id, tx in tuple(
        pending_arm_rig_cleanups.items()
    ):

        if tx.state != transaction_state_cls.CLEANUP_PENDING:
            raise RuntimeError(
                "Arm IK cleanup registry invariant violated: "
                f"transaction {tx_id} is registered with "
                f"state {tx.state}"
            )

        if (arm_ptr and tx.arm_ptr == arm_ptr) or (
            session_id is not None and getattr(tx, "session_id", None) == session_id
        ):
            blocking_transactions.append(tx_id)

    if blocking_transactions:
        raise RuntimeError(
            "Arm IK write blocked: unresolved cleanup "
            "for the same Armature; pending transactions="
            + ",".join(sorted(blocking_transactions))
        )


# [INTRODUCED 2026-11-24T13:16:00+08:00]
# NODE: 10-B / L1-03
# FUNCTION: _assert_arm_rig_failed_isolation_gate
# PURPOSE: 检查 FAILED 隔离注册表与会话隔离状态，阻断已被隔离骨架会话的新独立写入
# REASON: 将外层事务 FAILED Isolation Gate 迁入 Layer 1，并复用 Layer 2 已有隔离注册表及状态枚举
def _assert_arm_rig_failed_isolation_gate(
    arm: Any,
    session_record: Any,
    *,
    isolated_failed_armatures: Dict[str, Any],
    armature_isolation_state_cls: Any,
    failed_transaction_class_cls: Any,
) -> None:
    """
    Reject new independent writes while the same Armature session identity
    is isolated in _ISOLATED_FAILED_ARMATURES (FAILED-B / FAILED-C / FAILED-D).
    """
    session_id = session_record.registry_session_id
    iso_rec = isolated_failed_armatures.get(session_id)
    if iso_rec is not None or session_record.isolation_state != armature_isolation_state_cls.NONE:
        failure_class = (
            iso_rec.get("failure_class")
            if iso_rec is not None
            else (
                failed_transaction_class_cls.FAILED_D.value
                if session_record.isolation_state in (
                    armature_isolation_state_cls.TOMBSTONED_FAILED_D,
                    armature_isolation_state_cls.ARCHIVED_RETIRED,
                )
                else session_record.isolation_state.value
            )
        )
        tx_id = iso_rec.get("transaction_id", "<unknown>") if iso_rec is not None else "<unknown>"
        iso_state = (
            iso_rec.get("isolation_state")
            if iso_rec is not None
            else session_record.isolation_state.value
        )
        raise RuntimeError(
            "Arm IK write blocked: Armature session is isolated due to prior FAILED transaction "
            f"(failure_class={failure_class}, isolation_state={iso_state}, "
            f"transaction_id={tx_id}, registry_session_id={session_id})"
        )


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: _assert_existing_session_admission
# PURPOSE: 在控制器枚举前对已匹配隔离条件的历史 Session 执行既有 Cleanup Gate 与 FAILED Isolation Gate 预检
# REASON: 将 Layer 4 setup_arm_ik 内联 Session 门禁预检迁入 Layer 1，保持条件门禁触发语义和 break 顺序
def _assert_existing_session_admission(
    arm: Any,
    *,
    managed_armature_identities: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Any],
    armature_isolation_state_cls: Any,
    assert_arm_rig_cleanup_gate: Callable[..., None],
    assert_arm_rig_failed_isolation_gate: Callable[..., None],
) -> None:
    """Enforce existing cleanup and FAILED isolation gates before controller ownership object enumeration."""
    for rec in managed_armature_identities.values():
        if rec.original_blender_ref is arm:
            if (
                rec.isolation_state != armature_isolation_state_cls.NONE
                or rec.registry_session_id in isolated_failed_armatures
            ):
                assert_arm_rig_cleanup_gate(arm, rec)
                assert_arm_rig_failed_isolation_gate(arm, rec)
            break


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: _assert_admission_identity_valid
# PURPOSE: 在外层事务准入身份验证失败时区分不确定读与确定无效身份并触发既有 FAILED-D 隔离及拒绝异常
# REASON: 将外层事务身份无效拒绝分支迁入 Layer 1，维持原有异常处理及 FAILED-D 隔离调用顺序而不修改隔离实现
def _assert_admission_identity_valid(
    arm: Any,
    session_rec: Any,
    admission_id_check: Dict[str, Any],
    *,
    identity_failure_is_uncertain: Callable[[Dict[str, Any]], bool],
    transaction_context_cls: Callable[..., Any],
    transaction_state_cls: Any,
    failed_transaction_class_cls: Any,
    record_armature_failure_isolation_by_coordinator: Callable[..., Any],
) -> None:
    """Reject outermost transaction admission when session identity verification fails."""
    if not admission_id_check["is_valid"]:
        if identity_failure_is_uncertain(admission_id_check):
            # Admission is before snapshot/business writes. An indeterminate read
            # denies this attempt but does not permanently isolate a healthy rig.
            raise RuntimeError(
                "Arm IK write blocked: ARMATURE_IDENTITY_UNVERIFIED_AT_ADMISSION "
                f"(registry_session_id={session_rec.registry_session_id}): "
                + "; ".join(admission_id_check["reasons"])
            )
        dead_tx = transaction_context_cls(arm, session_record=session_rec)
        dead_tx.state = transaction_state_cls.FAILED
        record_armature_failure_isolation_by_coordinator(
            session_rec=session_rec,
            tx=dead_tx,
            failure_class=failed_transaction_class_cls.FAILED_D,
            primary_exception=RuntimeError("; ".join(admission_id_check["reasons"])),
            evidence_status="ARMATURE_IDENTITY_INVALID_AT_ADMISSION",
            missing_evidence_reasons=admission_id_check["reasons"],
        )
        raise RuntimeError(
            "Arm IK write blocked: Armature session identity invalid at admission "
            f"(failure_class=FAILED-D, transaction_id={dead_tx.tx_id}, "
            f"registry_session_id={session_rec.registry_session_id}): "
            + "; ".join(admission_id_check["reasons"])
        )
