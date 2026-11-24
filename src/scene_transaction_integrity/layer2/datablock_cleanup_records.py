"""DataBlock cleanup authorization lookup and outcome recording migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L6-02)."""

from typing import Any, Dict, Optional


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _find_datablock_cleanup_authorization
# PURPOSE: 在当前事务授权列表中按原指针或原引用查找匹配的 DataBlock 删除授权记录
# REASON: 将 DataBlock 授权查询从 arm_ik.py 迁入 Layer 2，保持原记录只读返回语义与禁止新授权签发边界
def _find_datablock_cleanup_authorization(
    tx: Any,
    data_ptr: Any,
    target_data: Any,
) -> Optional[Dict[str, Any]]:
    """Find the original transaction-local DataBlock authorization."""
    matching_auth = None
    for auth in tx.datablock_authorizations:
        if not isinstance(auth, dict):
            continue
        if auth.get("authorized_transaction") != tx.tx_id:
            continue
        auth_ptr = auth.get("original_pointer")
        auth_ref = auth.get("original_reference")
        if (
            (auth_ptr is not None and auth_ptr == data_ptr)
            or (auth_ref is not None and auth_ref == target_data)
        ):
            matching_auth = auth
            break

    return matching_auth


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _record_preserved_datablock_cleanup
# PURPOSE: 在缺乏删除授权时去重并追加 PRESERVED_NO_DELETE_AUTHORITY 清理结果记录
# REASON: 将无授权保留结果登记迁入 Layer 2，保留含 original_reference 的原始记录结构及惰性字段读取位置
def _record_preserved_datablock_cleanup(
    tx: Any,
    data_ref: Any,
    data_ptr: Any,
    data_name: Any,
    target_data: Any,
    target_coll: Any,
) -> None:
    """Record the existing no-delete-authority preservation outcome."""
    already_recorded = any(
        (
            o.get("resource_pointer") == data_ptr
            or (
                data_ref is not None
                and o.get("original_reference") == data_ref
            )
        )
        and o.get("tx_id") == tx.tx_id
        for o in tx.datablock_cleanup_outcomes
    )

    if not already_recorded:
        tx.datablock_cleanup_outcomes.append({
            "action": "PRESERVED",
            "status": "PRESERVED_NO_DELETE_AUTHORITY",
            "reason": "NO_DELETE_AUTHORITY",
            "resource_kind": getattr(
                target_coll, "name", type(target_data).__name__
            ),
            "resource_name": data_name,
            "resource_pointer": data_ptr,
            "original_reference": data_ref,
            "tx_id": tx.tx_id,
        })


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _record_deleted_datablock_cleanup
# PURPOSE: 在受权物理删除且核验缺席后去重并追加 PHYSICALLY_DELETED 清理结果记录
# REASON: 将成功删除结果登记迁入 Layer 2，严格保留不含 original_reference 的原始记录结构
def _record_deleted_datablock_cleanup(
    tx: Any,
    data_ref: Any,
    data_ptr: Any,
    data_name: Any,
    target_data: Any,
    target_coll: Any,
) -> None:
    """Record the existing physically deleted outcome."""
    already_recorded = any(
        (
            o.get("resource_pointer") == data_ptr
            or (
                data_ref is not None
                and o.get("original_reference") == data_ref
            )
        )
        and o.get("tx_id") == tx.tx_id
        for o in tx.datablock_cleanup_outcomes
    )

    if not already_recorded:
        tx.datablock_cleanup_outcomes.append({
            "action": "DELETED",
            "status": "PHYSICALLY_DELETED",
            "reason": "AUTHORIZED_CLEANUP",
            "resource_kind": getattr(
                target_coll, "name", type(target_data).__name__
            ),
            "resource_name": data_name,
            "resource_pointer": data_ptr,
            "tx_id": tx.tx_id,
        })
