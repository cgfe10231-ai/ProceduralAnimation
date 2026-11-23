"""Constraint creation, 8-tuple provenance receipt minting, and compensation boundary migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-07)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-23T21:38:30+08:00]
# NODE: 10-B / L3-07
# FUNCTION: _authorized_create_constraint
# PURPOSE: Verify transaction and PoseBone ownership, construct Constraint, mint 8-tuple creation receipt, and execute pre/post-registration verification and compensation boundary
# REASON: Migrate Constraint resource creation from src/rig/arm_ik.py into Layer 3 along the normal Blender resource creation chain while preserving original failure compensation boundary
def _authorized_create_constraint(
    pbone: bpy.types.PoseBone,
    con_type: str,
    con_name: str,
    active_tx: Optional[Any] = None,
    arm: Optional[bpy.types.Object] = None,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    ensure_armature_session_identity: Callable[[bpy.types.Object], Any],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    cleanup_failed_constraint_creation: Callable[..., None],
) -> bpy.types.Constraint:
    """Layer 3 authorized creation of a managed constraint on a pose bone.

    Enforces:
    1. Active transaction in ACTIVE state.
    2. Armature session identity matches transaction.
    3. Pose bone belongs to armature.
    4. Pose bone identity is live and verifiable.
    5. Constraint type must be 'IK' or 'COPY_ROTATION'.
    6. No duplicate live constraint with same identity and type.
    7. Immediate registration before any property assignment.
    8. Safe cleanup if registration fails.
    """
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    if active_tx is None:
        raise RuntimeError("Cannot create constraint: active transaction is required")

    if active_tx.state != transaction_state_cls.ACTIVE:
        raise RuntimeError(
            f"Cannot create constraint: transaction is in state {active_tx.state}, expected ACTIVE"
        )

    if not active_transaction_stack or active_transaction_stack[-1] is not active_tx:
        raise RuntimeError("Cannot create constraint: active transaction is not top of transaction stack")

    if con_type not in ("IK", "COPY_ROTATION"):
        raise ValueError(f"Unauthorized constraint type for arm IK rig: {con_type}")

    # Armature identity and session verification
    target_arm = arm if arm is not None else getattr(active_tx, "arm", None)
    if target_arm is not None:
        arm_ptr = target_arm.as_pointer() if hasattr(target_arm, "as_pointer") else None
        if active_tx.arm_ptr is not None and arm_ptr is not None and arm_ptr != active_tx.arm_ptr:
            raise RuntimeError("Armature identity does not match active transaction")
        try:
            target_session = ensure_armature_session_identity(target_arm)
            if target_session.registry_session_id != active_tx.session_id:
                raise RuntimeError("Armature session ID does not match active transaction")
        except Exception as sess_exc:
            raise RuntimeError(f"Armature session identity verification failed: {sess_exc}") from sess_exc

    # Pose bone verification
    try:
        pbone_ptr = int(pbone.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as re:
        raise RuntimeError(f"PoseBone reference is dead: {re}") from re

    if target_arm is not None and hasattr(target_arm, "pose") and target_arm.pose is not None:
        if pbone.name not in target_arm.pose.bones or target_arm.pose.bones[pbone.name] != pbone:
            raise RuntimeError(f"PoseBone '{pbone.name}' does not belong to active armature")

    # Check no duplicate live constraint with same name and type
    for existing in pbone.constraints:
        if existing.name == con_name and existing.type == con_type:
            raise RuntimeError(
                f"Duplicate constraint creation: '{con_name}' ({con_type}) already exists on bone '{pbone.name}'"
            )

    # [INTRODUCED 2026-11-16T19:15:00+08:00]
    # FUNCTION: _authorized_create_constraint
    # PURPOSE: Validate receipt ledger structure, seal existence, and registry structure before physical C-API constraint creation
    # REASON: Task 10-B fix-4 Round 1/2, reject malformed receipt ledger or missing seal prior to Blender constraint creation
    receipts = getattr(active_tx, "_constraint_creation_receipts", None)
    if (receipts is None or not isinstance(receipts, dict)
            or any(type(k) is not int or k <= 0 or not isinstance(v, tuple) or len(v) != 8
                   for k, v in receipts.items())):
        raise RuntimeError("CONSTRAINT_CREATION_RECEIPT_LEDGER_UNAVAILABLE")

    seal = getattr(active_tx, "_constraint_receipt_seal", None)
    if seal is None:
        raise RuntimeError("CONSTRAINT_CREATION_RECEIPT_SEAL_UNAVAILABLE")

    registry = getattr(active_tx, "created_constraints", None)
    if not isinstance(registry, list) or any(not isinstance(rec, dict) for rec in registry):
        raise RuntimeError("CONSTRAINT_CREATION_REGISTRY_MALFORMED")

    tx_session_id = getattr(active_tx, "session_id", None)
    tx_id_val = getattr(active_tx, "tx_id", None)
    if not isinstance(tx_session_id, str) or not tx_session_id or not isinstance(tx_id_val, str) or not tx_id_val:
        raise RuntimeError("CONSTRAINT_CREATION_TRANSACTION_IDENTITY_UNAVAILABLE")

    # Capture the complete owner-chain identity BEFORE the creation C-API.
    # This local witness prevents any name-matched pre-existing constraint
    # from being considered removable in a fault-injection window.
    try:
        before_ptrs = frozenset(int(c.as_pointer()) for c in pbone.constraints)
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("CONSTRAINT_CREATION_BASELINE_UNREADABLE") from exc

    con = pbone.constraints.new(type=con_type)
    con_ptr: Optional[int] = None
    try:
        try:
            con_ptr = int(con.as_pointer())
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
            # No stable identity is available; refusing deletion is safer than
            # substituting another constraint in the owning PoseBone chain.
            raise RuntimeError("CONSTRAINT_CREATION_IDENTITY_UNREADABLE: refusing name-based cleanup") from exc
        if con_ptr <= 0 or con_ptr in before_ptrs or con_ptr in receipts:
            raise RuntimeError("CONSTRAINT_CREATION_IDENTITY_COLLISION: refusing cleanup without provenance")

        # [INTRODUCED 2026-11-16T18:15:00+08:00]
        # FUNCTION: _authorized_create_constraint
        # PURPOSE: Mint independent provenance receipt within the exception compensation scope
        # REASON: Task 10-B fix-4, ensure receipt write failures enter compensation to prevent uncompensated orphans
        live_receipts = getattr(active_tx, "_constraint_creation_receipts", None)
        live_seal = getattr(active_tx, "_constraint_receipt_seal", None)
        if live_receipts is not receipts or not isinstance(live_receipts, dict) or live_seal is not seal or live_seal is None:
            raise RuntimeError("CONSTRAINT_CREATION_RECEIPT_LEDGER_UNAVAILABLE")

        receipt = (
            con,
            con_ptr,
            pbone,
            pbone_ptr,
            tx_session_id,
            tx_id_val,
            live_seal,
            before_ptrs,
        )
        live_receipts[con_ptr] = receipt

        # Name setting is also fallible and must be within the compensation
        # window, rather than creating an unregistered orphan on exception.
        con.name = con_name
        trigger_fault_injection(
            "character_constraint_after_creation_before_registration",
            {"pbone": pbone, "con": con, "tx": active_tx, "name": con_name, "type": con_type},
        )

        # Registration is fallible. Even a register() that raises after append
        # is handled by the single cleanup decision below.
        active_tx.register_created_constraint(pbone, con)
        records = [rec for rec in active_tx.created_constraints
                   if isinstance(rec, dict) and rec.get("con_ptr") == con_ptr]
        if (len(records) != 1 or records[0].get("con_ref") != con
                or records[0].get("pbone") != pbone
                or records[0].get("bone_name") != pbone.name):
            raise RuntimeError(f"Constraint '{con_name}' registration verification failed")

        trigger_fault_injection(
            "character_constraint_after_registration_before_config",
            {"pbone": pbone, "con": con, "tx": active_tx, "name": con_name, "type": con_type},
        )
        return con
    except BaseException as creation_exc:
        if con_ptr is not None and con_ptr > 0 and con_ptr not in before_ptrs:
            try:
                cleanup_failed_constraint_creation(
                    pbone, con, con_ptr, pbone_ptr, before_ptrs, active_tx,
                )
            except BaseException as cleanup_exc:
                raise RuntimeError(
                    "CONSTRAINT_CREATION_CLEANUP_FAILED: "
                    f"original={type(creation_exc).__name__}: {creation_exc}; "
                    f"cleanup={type(cleanup_exc).__name__}: {cleanup_exc}"
                ) from cleanup_exc
        raise
