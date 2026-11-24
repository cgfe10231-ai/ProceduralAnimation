"""Shared authorized Constraint removal across ROLLBACK and POST_COMMIT_CLEANUP phases migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-11)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _resolve_rollback_constraint_removal_record
# PURPOSE: 在 ROLLBACK 阶段验证 ROLLING_BACK 状态、活动栈成员资格、唯一注册记录、八元组创建凭证与 seal、PoseBone/基线/快照排除并解析待删约束记录
# REASON: 将 ROLLBACK 约束删除授权解析从 _authorized_remove_constraint 拆入 Layer 3 内部 Resolver，不混合暂存清理授权并保持零额外删除入口
def _resolve_rollback_constraint_removal_record(
    pbone: Any,
    con_record_or_ref: Any,
    active_tx: Any,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
) -> Dict[str, Any]:
    """Resolve and verify the unique ROLLBACK constraint removal record and receipt."""
    # [INTRODUCED 2026-11-16T17:18:48+08:00]
    # FUNCTION: _authorized_remove_constraint
    # PURPOSE: Verify ROLLING_BACK state, active stack ownership, registry uniqueness, and creation receipt provenance
    # REASON: Task 10-B fix-4, require independent provenance receipts for constraint rollback removal
    if active_tx.state != transaction_state_cls.ROLLING_BACK:
        raise RuntimeError(
            f"Unauthorized constraint removal in ROLLBACK phase: transaction state is {active_tx.state}, expected ROLLING_BACK"
        )
    if not active_transaction_stack or active_tx not in active_transaction_stack:
        raise RuntimeError(
            "Unauthorized constraint removal: transaction does not belong to active transaction stack"
        )

    allowed_records = list(getattr(active_tx, "created_constraints", []))
    matching_records = []
    if isinstance(con_record_or_ref, dict):
        rec_ptr = con_record_or_ref.get("con_ptr")
        matching_records = [rec for rec in allowed_records if rec.get("con_ptr") == rec_ptr]
    else:
        try:
            cand_ptr = con_record_or_ref.as_pointer()
        except ReferenceError:
            cand_ptr = None
        matching_records = [
            rec for rec in allowed_records
            if rec.get("con_ref") == con_record_or_ref or (cand_ptr is not None and rec.get("con_ptr") == cand_ptr)
        ]

    if len(matching_records) != 1:
        raise RuntimeError(
            f"Unauthorized constraint removal: expected exactly 1 registration record in ROLLBACK, got {len(matching_records)}"
        )
    target_record = matching_records[0]

    rec_ptr = target_record.get("con_ptr")
    rec_con_ref = target_record.get("con_ref")
    rec_pbone = target_record.get("pbone")

    receipts = getattr(active_tx, "_constraint_creation_receipts", {})
    if not isinstance(receipts, dict) or rec_ptr not in receipts:
        raise RuntimeError(
            f"Unauthorized constraint removal: no creation receipt found for constraint ptr={rec_ptr}"
        )

    receipt = receipts[rec_ptr]
    if not isinstance(receipt, tuple) or len(receipt) != 8:
        raise RuntimeError("Unauthorized constraint removal: creation receipt length must be exactly 8")

    rc_con, rc_con_ptr, rc_pbone, rc_pbone_ptr, rc_session_id, rc_tx_id, rc_seal, rc_before_ptrs = receipt

    if rc_seal is not getattr(active_tx, "_constraint_receipt_seal", None):
        raise RuntimeError("Unauthorized constraint removal: creation receipt seal mismatch")
    if rc_tx_id != active_tx.tx_id:
        raise RuntimeError(f"Unauthorized constraint removal: tx_id mismatch: {rc_tx_id} != {active_tx.tx_id}")
    if rc_session_id != active_tx.session_id:
        raise RuntimeError(f"Unauthorized constraint removal: session_id mismatch: {rc_session_id} != {active_tx.session_id}")
    if rc_con_ptr != rec_ptr or rc_con != rec_con_ref:
        raise RuntimeError("Unauthorized constraint removal: constraint reference or pointer mismatch with receipt")
    if rc_pbone != rec_pbone:
        raise RuntimeError("Unauthorized constraint removal: pose bone reference mismatch with receipt")
    if pbone is not None and rc_pbone != pbone:
        raise RuntimeError("Unauthorized constraint removal: target pose bone mismatch with receipt")

    if type(rc_pbone_ptr) is not int or rc_pbone_ptr <= 0:
        raise RuntimeError("Unauthorized constraint removal: invalid pose bone pointer in receipt")
    target_pbone = pbone if pbone is not None else rec_pbone
    try:
        target_pbone_ptr = int(target_pbone.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Unauthorized constraint removal: pose bone pointer unreadable: {exc}") from exc
    if target_pbone_ptr != rc_pbone_ptr:
        raise RuntimeError(
            f"Unauthorized constraint removal: pose bone pointer mismatch: live={target_pbone_ptr} != receipt={rc_pbone_ptr}"
        )

    if not isinstance(rc_before_ptrs, frozenset):
        raise RuntimeError("Unauthorized constraint removal: creation receipt before_ptrs must be frozenset")

    snapshot = getattr(active_tx, "snapshot", None)
    if snapshot is None or not isinstance(snapshot, dict):
        raise RuntimeError("Unauthorized constraint removal: active transaction missing trusted snapshot")
    if active_tx.snapshot is not snapshot:
        raise RuntimeError("Unauthorized constraint removal: transaction snapshot identity mismatch")

    for b_name_snap, b_data_snap in snapshot.get("pose_bones", {}).items():
        if isinstance(b_data_snap, dict):
            for sc in b_data_snap.get("constraints", []):
                if isinstance(sc, dict):
                    if sc.get("con_ptr") == rec_ptr or sc.get("con_ref") == rec_con_ref:
                        raise RuntimeError(
                            f"Unauthorized constraint removal: constraint ptr={rec_ptr} is an original snapshot constraint; deletion rejected"
                        )

    if rec_ptr in rc_before_ptrs:
        raise RuntimeError(
            f"Unauthorized constraint removal: constraint ptr={rec_ptr} was in pre-creation baseline; deletion rejected"
        )

    return target_record


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _resolve_stashed_constraint_removal_record
# PURPOSE: 在 POST_COMMIT_CLEANUP 阶段合并 stashed_constraints 与 uncleaned_stashed_constraints 并按首个匹配返回待删约束记录
# REASON: 将提交后暂存约束删除授权解析拆入 Layer 3 内部 Resolver，保持与 ROLLBACK 授权语义严格隔离且不做未授权去重
def _resolve_stashed_constraint_removal_record(
    con_record_or_ref: Any,
    active_tx: Any,
    phase: str,
) -> Dict[str, Any]:
    """Resolve the first matching POST_COMMIT_CLEANUP stashed constraint record."""
    target_record: Optional[Dict[str, Any]] = None
    allowed_records = (
        list(getattr(active_tx, "stashed_constraints", []))
        + list(
            getattr(
                active_tx,
                "uncleaned_stashed_constraints",
                [],
            )
        )
    )
    if isinstance(con_record_or_ref, dict):
        rec_ptr = con_record_or_ref.get("con_ptr")
        for rec in allowed_records:
            if rec.get("con_ptr") == rec_ptr:
                target_record = rec
                break
    else:  # Constraint object
        try:
            cand_ptr = con_record_or_ref.as_pointer()
        except ReferenceError:
            cand_ptr = None
        for rec in allowed_records:
            if rec.get("con_ref") == con_record_or_ref or (cand_ptr is not None and rec.get("con_ptr") == cand_ptr):
                target_record = rec
                break

    if target_record is None:
        raise RuntimeError(
            f"Unauthorized constraint removal: resource not found in active transaction records for phase {phase}"
        )

    return target_record


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _authorized_remove_constraint
# PURPOSE: 按 ROLLBACK 与 POST_COMMIT_CLEANUP 两阶段各自解析受权约束记录，核验 PoseBone 与指针身份、触发故障注入并执行共享物理删除及删后验证
# REASON: 将 Cleanup 与 Rollback 共用的唯一受权约束删除入口迁入 Layer 3，同时由 arm_ik.py 兼容代理保持回滚及清理调用链不变
def _authorized_remove_constraint(
    pbone: bpy.types.PoseBone,
    con_record_or_ref: Any,
    phase: str,
    active_tx: Optional[Any] = None,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    trigger_fault_injection: Callable[..., None],
) -> bool:
    """Layer 3 authoritative removal of a managed constraint.

    Only allowed in:
    1. phase == "ROLLBACK": for constraints in active_tx.created_constraints.
    2. phase == "POST_COMMIT_CLEANUP": for constraints in active_tx.stashed_constraints.

    Requires joint verification of:
    - live reference
    - pointer identity
    - owning pose bone
    - transaction registration record
    """
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    if active_tx is None:
        raise RuntimeError("Active transaction required for authorized constraint removal")

    if phase not in ("ROLLBACK", "POST_COMMIT_CLEANUP"):
        raise RuntimeError(f"Unauthorized constraint removal phase: '{phase}'")

    # Resolve the transaction record
    target_record: Optional[Dict[str, Any]] = None

    if phase == "ROLLBACK":
        target_record = _resolve_rollback_constraint_removal_record(
            pbone,
            con_record_or_ref,
            active_tx,
            active_transaction_stack=active_transaction_stack,
            transaction_state_cls=transaction_state_cls,
        )
    else:
        target_record = _resolve_stashed_constraint_removal_record(
            con_record_or_ref,
            active_tx,
            phase,
        )

    # Verify bone identity
    rec_pbone = target_record.get("pbone")
    rec_bone_name = target_record.get("bone_name")
    if pbone is None and rec_pbone is not None:
        pbone = rec_pbone
    if pbone is None:
        raise RuntimeError("Owning PoseBone is required for constraint removal")

    if rec_pbone is not None and rec_pbone != pbone:
        raise RuntimeError("Constraint record owning PoseBone reference mismatch")
    if rec_bone_name is not None and pbone.name != rec_bone_name:
        raise RuntimeError(f"Constraint record bone name mismatch: {pbone.name} != {rec_bone_name}")

    expected_ptr = target_record.get("con_ptr")
    con_ref = target_record.get("con_ref", target_record.get("con"))

    # Check if constraint is already deleted (idempotent removal)
    if con_ref is not None:
        try:
            live_ptr = con_ref.as_pointer()
            if expected_ptr is not None and live_ptr != expected_ptr:
                raise RuntimeError("Live constraint pointer changed unexpectedly")
        except ReferenceError:
            orig_name = target_record.get("orig_name")
            if any((orig_name and c.name == orig_name) or (expected_ptr and c.as_pointer() == expected_ptr) for c in pbone.constraints):
                raise RuntimeError("Stashed constraint original reference invalid")
            return True

    # Search for matching candidate in pbone.constraints
    matched_candidate = None
    for cand in list(pbone.constraints):
        try:
            if expected_ptr is not None and cand.as_pointer() == expected_ptr:
                if con_ref is not None and cand != con_ref:
                    raise RuntimeError("Constraint pointer matches but live reference differs")
                matched_candidate = cand
                break
            elif con_ref is not None and cand == con_ref:
                matched_candidate = cand
                break
        except ReferenceError:
            continue

    if matched_candidate is None:
        # Resource is already absent. Verify no substitute is touched.
        return True

    # Trigger fault injection before physical removal
    trigger_fault_injection(
        "during_constraint_removal",
        {
            "pbone": pbone,
            "con": matched_candidate,
            "record": target_record,
            "phase": phase,
            "tx": active_tx,
        },
    )

    # Physical removal via Blender C-API
    pbone.constraints.remove(matched_candidate)

    # Verify removal: re-enumerate constraints on pbone
    still_present = any(
        (expected_ptr is not None and c.as_pointer() == expected_ptr) or (con_ref is not None and c == con_ref)
        for c in pbone.constraints
    )
    if still_present:
        raise RuntimeError(f"Constraint removal verification failed: constraint still present on '{pbone.name}'")

    return True
