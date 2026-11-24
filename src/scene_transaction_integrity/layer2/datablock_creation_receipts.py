"""Type-A DataBlock creation receipt and authorization ledger helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L3-11)."""

from typing import Any, Dict, Optional


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _register_type_a_datablock_receipt
# PURPOSE: 向当前事务私有凭证表被动写入由新建 Mesh 产生的四元组 Type-A 创建凭证（含原 _type_a_datablock_receipt_seal）
# REASON: 将 Type-A Receipt 写入归入 Layer 2 被动登记，保持创建验证与异常赋值边界在 Layer 3 且不生成新 seal
def _register_type_a_datablock_receipt(
    tx: Any,
    new_ptr: int,
    mesh: Any,
) -> None:
    tx._type_a_datablock_receipts[new_ptr] = (
        mesh,
        tx.session_id,
        tx.tx_id,
        tx._type_a_datablock_receipt_seal,
    )


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _register_type_a_datablock_authorization
# PURPOSE: 将 Layer 3 可信 Type-A Mesh 创建路径构造的原始授权字典原样追加至当前事务授权列表
# REASON: 将 Type-A 删除授权列表追加归入 Layer 2 被动登记，维持原字典对象身份并仅供 Layer 3 创建路径调用
def _register_type_a_datablock_authorization(
    tx: Any,
    auth: Dict[str, Any],
) -> None:
    tx.datablock_authorizations.append(auth)


# [INTRODUCED 2026-11-24T20:06:00+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _revoke_type_a_datablock_creation_records
# PURPOSE: 在 Type-A Mesh 局部创建失败补偿期间按先凭证后授权列表的顺序撤销已登记条目
# REASON: 将部分创建登记撤销归入 Layer 2，保持局部异常捕获边界及后续 Blender 零用户删除顺序在 Layer 3 不变
def _revoke_type_a_datablock_creation_records(
    tx: Any,
    new_ptr: Optional[int],
    mesh: Any,
    auth: Optional[Dict[str, Any]],
    receipt_registered: bool,
) -> None:
    if receipt_registered and new_ptr is not None:
        receipt = tx._type_a_datablock_receipts.get(new_ptr)
        if receipt is not None and receipt[0] == mesh:
            tx._type_a_datablock_receipts.pop(new_ptr, None)

    if auth is not None and auth in tx.datablock_authorizations:
        tx.datablock_authorizations.remove(auth)
