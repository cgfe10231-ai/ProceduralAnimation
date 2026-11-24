"""Authorized Type-A DataBlock creation and local failure compensation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-11)."""

from typing import Any, Dict, List

import bpy

from src.scene_transaction_integrity.layer2.datablock_creation_receipts import (
    _register_type_a_datablock_authorization,
    _register_type_a_datablock_receipt,
    _revoke_type_a_datablock_creation_records,
)


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _authorized_create_type_a_mesh
# PURPOSE: 在 ACTIVE 事务授权下创建新 Mesh、验证新鲜指针与零用户后登记独立 Type-A 四元组凭证与删除授权，并在失败时执行局部撤销与删除补偿
# REASON: 将 BUG-10 唯一 Type-A DataBlock 创建与本地失败补偿迁入 Layer 3，复用 Layer 2 被动凭证登记而不与提交后 DataBlock 清理混合
def _authorized_create_type_a_mesh(
    name: str,
    active_tx: Any,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    managed_armature_identities: Dict[str, Any],
) -> bpy.types.Mesh:
    """Create a transaction-owned Mesh with an identity-bound deletion receipt.

    Only this creation-returned Blender ID can receive TYPE_A_TX_CREATED
    authority. Observing an existing ID or appending an authorization dict
    never proves transaction creation.
    """
    if type(name) is not str or not name.strip():
        raise ValueError("TYPE_A_CREATE_DENIED: Mesh name must be nonempty")
    if (active_tx is None or not active_transaction_stack
            or active_transaction_stack[-1] is not active_tx
            or active_tx.state != transaction_state_cls.ACTIVE):
        raise RuntimeError("TYPE_A_CREATE_DENIED: owning ACTIVE transaction required")
    if (not isinstance(active_tx._type_a_datablock_receipts, dict)
            or not isinstance(active_tx.datablock_authorizations, list)
            or active_tx.session_record is None
            or managed_armature_identities.get(active_tx.session_id) is not active_tx.session_record
            or active_tx.session_record.original_blender_ref is not active_tx.arm):
        raise RuntimeError("TYPE_A_CREATE_DENIED: transaction provenance/ledger invalid")
    before = frozenset(int(item.as_pointer()) for item in bpy.data.meshes)
    mesh = bpy.data.meshes.new(name)
    new_ptr = None
    auth = None
    receipt_registered = False
    try:
        new_ptr = int(mesh.as_pointer())
        if (new_ptr <= 0 or new_ptr in before
                or new_ptr in active_tx._type_a_datablock_receipts
                or not any(int(item.as_pointer()) == new_ptr and item == mesh
                           for item in bpy.data.meshes)
                or int(mesh.users) != 0):
            raise RuntimeError("TYPE_A_CREATE_DENIED: fresh Mesh identity is unproven")
        _register_type_a_datablock_receipt(
            active_tx,
            new_ptr,
            mesh,
        )
        receipt_registered = True
        auth = {
            "resource_kind": "meshes",
            "original_reference": mesh,
            "original_pointer": new_ptr,
            "provenance": "TYPE_A_TX_CREATED",
            "authorization_source": "TX_CREATE_RECEIPT",
            "authorization_scope": "PHYSICAL_DELETE_IF_ZERO_USERS",
            "authorized_transaction": active_tx.tx_id,
            "expected_lifecycle": "COMMITTED_CLEANUP",
        }
        _register_type_a_datablock_authorization(
            active_tx,
            auth,
        )
        return mesh
    except BaseException as creation_exc:
        # Compensate only the same newly-created zero-user ID. Never use name
        # matching or a pointer that existed before this creation call.
        cleanup_exc = None
        try:
            _revoke_type_a_datablock_creation_records(
                active_tx,
                new_ptr,
                mesh,
                auth,
                receipt_registered,
            )
            if (new_ptr is None or new_ptr in before or new_ptr <= 0
                    or int(mesh.as_pointer()) != new_ptr
                    or int(mesh.users) != 0
                    or not any(int(item.as_pointer()) == new_ptr and item == mesh
                               for item in bpy.data.meshes)):
                raise RuntimeError("TYPE_A_CREATE_CLEANUP_UNPROVEN: refusing deletion")
            bpy.data.meshes.remove(mesh, do_unlink=False)
            if any(int(item.as_pointer()) == new_ptr for item in bpy.data.meshes):
                raise RuntimeError("TYPE_A_CREATE_CLEANUP_FAILED: Mesh remains live")
        except BaseException as exc:
            cleanup_exc = exc
        if cleanup_exc is not None:
            raise RuntimeError(
                "TYPE_A_CREATE_AND_CLEANUP_FAILED: "
                f"original={type(creation_exc).__name__}: {creation_exc}; "
                f"cleanup={type(cleanup_exc).__name__}: {cleanup_exc}"
            ) from cleanup_exc
        raise
