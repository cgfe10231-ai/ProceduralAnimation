"""Constraint receipt verification and registry recording migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-09)."""

from typing import Any, Callable, List

import bpy


# [INTRODUCED 2026-11-23T21:58:00+08:00]
# NODE: 10-B / L2-09
# FUNCTION: _register_created_constraint
# PURPOSE: Verify ACTIVE Transaction, stack ownership, Armature Session, PoseBone belonging, Constraint/PoseBone dual identity checks, and 8-tuple creation receipt before appending created Constraint record to transaction Registry
# REASON: Migrate TransactionContext receipt verification and Constraint registration duty along the normal Constraint creation chain into Layer 2 while preserving original behavior verbatim
def _register_created_constraint(
    self: Any,
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    ensure_armature_session_identity: Callable[[bpy.types.Object], Any],
) -> None:
    """Register a constraint created by this transaction for identity-based ownership."""
    if self.state != transaction_state_cls.ACTIVE:
        raise RuntimeError(
            f"Constraint registration rejected: transaction state is {self.state}, expected ACTIVE"
        )

    if not active_transaction_stack or active_transaction_stack[-1] is not self:
        raise RuntimeError(
            "Constraint registration rejected: transaction is not top of active transaction stack"
        )

    session_id = self.session_id
    if not session_id or not self.session_record:
        raise RuntimeError(
            "Constraint registration rejected: missing armature session identity"
        )
    if self.arm is not None:
        try:
            cur_rec = ensure_armature_session_identity(self.arm)
            if cur_rec.registry_session_id != session_id:
                raise RuntimeError(
                    "Constraint registration rejected: armature session identity mismatch"
                )
        except Exception as e:
            raise RuntimeError(
                f"Constraint registration rejected: failed to verify armature session identity: {e}"
            ) from e

    if self.arm is None or not hasattr(self.arm, "pose") or self.arm.pose is None:
        raise RuntimeError(
            "Constraint registration rejected: active armature pose is unavailable"
        )
    if pbone.name not in self.arm.pose.bones or self.arm.pose.bones[pbone.name] != pbone:
        raise RuntimeError(
            f"Constraint registration rejected: PoseBone '{pbone.name}' does not belong to active armature"
        )

    try:
        con_ptr = int(con.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Constraint registration rejected: constraint reference is invalid or dead"
        ) from exc

    if con_ptr <= 0:
        raise RuntimeError(
            "Constraint registration rejected: invalid constraint pointer"
        )

    try:
        if not any(int(c.as_pointer()) == con_ptr for c in pbone.constraints):
            raise RuntimeError(
                f"Constraint registration rejected: constraint (ptr={con_ptr}) is not live on bone '{pbone.name}'"
            )
    except Exception as exc:
        raise RuntimeError(
            f"Constraint registration rejected: cannot enumerate constraints on bone '{pbone.name}': {exc}"
        ) from exc

    for record in self.created_constraints:
        if record.get("con_ptr") == con_ptr:
            raise RuntimeError(
                "Duplicate transaction constraint registration"
            )

    receipts = getattr(self, "_constraint_creation_receipts", None)
    if receipts is None or not isinstance(receipts, dict) or con_ptr not in receipts:
        raise RuntimeError(
            f"Constraint registration rejected: no creation receipt found for constraint ptr={con_ptr}"
        )

    receipt = receipts[con_ptr]
    if not isinstance(receipt, tuple) or len(receipt) != 8:
        raise RuntimeError(
            "Constraint registration rejected: creation receipt length must be exactly 8"
        )

    rc_con, rc_con_ptr, rc_pbone, rc_pbone_ptr, rc_session_id, rc_tx_id, rc_seal, rc_before_ptrs = receipt

    if rc_seal is not getattr(self, "_constraint_receipt_seal", None):
        raise RuntimeError(
            "Constraint registration rejected: creation receipt seal mismatch"
        )
    if rc_tx_id != self.tx_id:
        raise RuntimeError(
            f"Constraint registration rejected: creation receipt tx_id mismatch: {rc_tx_id} != {self.tx_id}"
        )
    if rc_session_id != self.session_id:
        raise RuntimeError(
            f"Constraint registration rejected: creation receipt session_id mismatch: {rc_session_id} != {self.session_id}"
        )
    if rc_con_ptr != con_ptr or rc_con != con:
        raise RuntimeError(
            "Constraint registration rejected: creation receipt constraint reference/pointer mismatch"
        )
    try:
        live_con_ptr = int(con.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Constraint registration rejected: live constraint pointer unreadable: {exc}") from exc
    if live_con_ptr != con_ptr:
        raise RuntimeError(
            f"Constraint registration rejected: live constraint pointer mismatch: live={live_con_ptr} != con_ptr={con_ptr}"
        )
    if rc_pbone != pbone:
        raise RuntimeError(
            "Constraint registration rejected: creation receipt pose bone mismatch"
        )
    if type(rc_pbone_ptr) is not int or rc_pbone_ptr <= 0:
        raise RuntimeError(
            "Constraint registration rejected: invalid pose bone pointer in creation receipt"
        )
    try:
        curr_pbone_ptr = int(pbone.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Constraint registration rejected: pose bone pointer unreadable: {exc}") from exc
    if curr_pbone_ptr != rc_pbone_ptr:
        raise RuntimeError(
            f"Constraint registration rejected: pose bone pointer mismatch: live={curr_pbone_ptr} != receipt={rc_pbone_ptr}"
        )
    if not isinstance(rc_before_ptrs, frozenset):
        raise RuntimeError(
            "Constraint registration rejected: creation receipt before_ptrs must be frozenset"
        )
    if con_ptr in rc_before_ptrs:
        raise RuntimeError(
            "Constraint registration rejected: constraint pointer was present in pre-creation baseline"
        )

    self.created_constraints.append({
        "pbone": pbone,
        "con_ref": con,
        "con_ptr": con_ptr,
        "created_name": con.name,
        "bone_name": pbone.name,
    })


# [INTRODUCED 2026-11-24T20:21:00+08:00]
# NODE: 10-B / L3-12
# FUNCTION: _revoke_compensated_constraint_creation_receipt
# PURPOSE: 在 Layer 3 完成未登记失败 Constraint 的物理删除及删后缺席核验后，被动从当前事务私有凭证表撤销原八元组创建凭证
# REASON: 将局部创建失败补偿成功后的原 Receipt 撤销归入 Layer 2 被动登记模块，避免 Layer 3 直接写入凭证字典同时严禁作为外部撤销 API
def _revoke_compensated_constraint_creation_receipt(
    active_tx: Any,
    expected_ptr: int,
) -> None:
    """Revoke the original receipt after verified local compensation."""
    if hasattr(active_tx, "_constraint_creation_receipts") and isinstance(
        active_tx._constraint_creation_receipts, dict
    ):
        active_tx._constraint_creation_receipts.pop(
            expected_ptr,
            None,
        )
