"""Stashed DataBlock lookup, delete-authority validation, and authorized removal migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L6-02)."""

from typing import Any, Callable, Dict, Tuple

import bpy


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _find_stashed_datablock
# PURPOSE: 按原八类 Blender DataBlock 集合顺序、指针优先引用备用定位废弃 DataBlock 及其所属集合
# REASON: 将 Blender DataBlock 查找逻辑从 arm_ik.py 迁入 Layer 3，保持原匹配条件及 ReferenceError 跳过行为
def _find_stashed_datablock(
    data_ref: Any,
    data_ptr: Any,
) -> Tuple[Any, Any]:
    """Locate the original stashed DataBlock and its collection."""
    target_data = None
    target_coll = None

    for coll_name in (
        "meshes",
        "curves",
        "lights",
        "cameras",
        "armatures",
        "lattices",
        "metaballs",
        "volumes",
    ):
        coll = getattr(bpy.data, coll_name, None)
        if coll is not None:
            for item in coll:
                try:
                    if data_ptr and item.as_pointer() == data_ptr:
                        target_data = item
                        target_coll = coll
                        break
                    elif data_ref is not None and item == data_ref:
                        target_data = item
                        target_coll = coll
                        break
                except ReferenceError:
                    continue

        if target_data is not None:
            break

    return target_data, target_coll


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _validate_stashed_datablock_delete_authority
# PURPOSE: 执行物理删除前的全部 Fail-Closed 授权、Type-A 凭证与 seal、指针集合及外部依赖验证
# REASON: 将 DataBlock 删除授权验证迁入 Layer 3 模块内部并强制先于物理删除执行，不修改既有授权语义
def _validate_stashed_datablock_delete_authority(
    tx: Any,
    matching_auth: Dict[str, Any],
    data_ptr: Any,
    data_name: Any,
    target_data: Any,
    target_coll: Any,
) -> None:
    """Validate independent DataBlock deletion authorization and dependency safety."""
    # Step 2: Strictly validate 12 conditions (Fail-Closed)
    required_fields = (
        "resource_kind",
        "original_reference",
        "original_pointer",
        "provenance",
        "authorization_source",
        "authorization_scope",
        "authorized_transaction",
        "expected_lifecycle",
    )
    missing_fields = [f for f in required_fields if f not in matching_auth]
    if missing_fields:
        raise RuntimeError(f"DataBlock authorization for {data_name} missing fields: {missing_fields}")

    if matching_auth["authorized_transaction"] != tx.tx_id:
        raise RuntimeError(f"DataBlock authorization tx mismatch: {matching_auth['authorized_transaction']} != {tx.tx_id}")

    if matching_auth.get("authorization_scope") != "PHYSICAL_DELETE_IF_ZERO_USERS":
        raise RuntimeError(f"DataBlock authorization scope invalid: {matching_auth.get('authorization_scope')}")

    provenance = matching_auth.get("provenance")
    if provenance not in ("TYPE_A_TX_CREATED", "TYPE_B_PRE_EXISTING_EXPLICIT_GRANT"):
        raise RuntimeError(f"DataBlock deletion authorization provenance rejected: {provenance}")

    if provenance == "TYPE_A_TX_CREATED":
        # Positive Type-A path: authorization comes from
        # this transaction's actual Mesh creation call,
        # never from a free-form claim or name.
        receipt = tx._type_a_datablock_receipts.get(data_ptr)
        if (not isinstance(receipt, tuple) or len(receipt) != 4
                or receipt[0] != target_data
                or receipt[1] != tx.session_id
                or receipt[2] != tx.tx_id
                or receipt[3] is not tx._type_a_datablock_receipt_seal
                or matching_auth.get("authorization_source") != "TX_CREATE_RECEIPT"
                or matching_auth.get("resource_kind") != "meshes"
                or matching_auth.get("original_reference") != target_data
                or matching_auth.get("original_pointer") != data_ptr
                or not any(int(item.as_pointer()) == data_ptr and item == target_data
                           for item in bpy.data.meshes)):
            raise RuntimeError(
                f"DataBlock {data_name} claims TYPE_A_TX_CREATED but lacks credible transaction creation provenance"
            )
    elif provenance == "TYPE_B_PRE_EXISTING_EXPLICIT_GRANT":
        raise RuntimeError(
            f"DATA_BLOCK_DELETE_AUTHORITY_UNPROVEN: {data_name}: "
            "TYPE_B deletion requires verified authorization "
            "from a trusted issuer; authorization_source "
            "string is not sufficient proof"
        )

    orig_ref = matching_auth.get("original_reference")
    if orig_ref is None:
        raise RuntimeError(f"DataBlock authorization original_reference is None")
    try:
        _ = getattr(orig_ref, "name")
    except Exception as ref_err:
        raise RuntimeError(f"DataBlock original_reference is invalid or dead: {ref_err}")

    try:
        live_ptr = target_data.as_pointer()
    except Exception as ptr_err:
        raise RuntimeError(f"Fail-closed: failed to read live pointer for {data_name}: {ptr_err}")

    if matching_auth.get("original_pointer") != live_ptr:
        raise RuntimeError(f"DataBlock original_pointer mismatch: {matching_auth.get('original_pointer')} != {live_ptr}")
    if data_ptr is not None and data_ptr != live_ptr:
        raise RuntimeError(f"DataBlock stashed pointer mismatch: {data_ptr} != {live_ptr}")

    if target_coll is None:
        raise RuntimeError(f"DataBlock {data_name} collection not found in bpy.data")
    try:
        item_in_coll = any(item.as_pointer() == live_ptr for item in target_coll)
    except Exception as coll_err:
        raise RuntimeError(f"Fail-closed: failed to enumerate collection for {data_name}: {coll_err}")
    if not item_in_coll:
        raise RuntimeError(f"DataBlock {data_name} does not exist in collection {target_coll}")

    if orig_ref != target_data:
        raise RuntimeError(f"DataBlock current live reference does not match original_reference")

    try:
        user_count = target_data.users
    except Exception as u_err:
        raise RuntimeError(f"Fail-closed: failed to read users attribute on {data_name}: {u_err}")
    if user_count != 0:
        raise RuntimeError(f"DataBlock {data_name} cannot be deleted: users count is {user_count} > 0")

    try:
        fake_user = target_data.use_fake_user
    except Exception as fu_err:
        raise RuntimeError(f"Fail-closed: failed to read use_fake_user attribute on {data_name}: {fu_err}")
    if fake_user is not False:
        raise RuntimeError(f"DataBlock {data_name} has use_fake_user == True; cannot delete")

    try:
        lib = target_data.library
    except Exception as lib_err:
        raise RuntimeError(f"Fail-closed: failed to read library attribute on {data_name}: {lib_err}")
    if lib is not None:
        raise RuntimeError(f"DataBlock {data_name} belongs to library {lib}; cannot delete")

    try:
        if hasattr(target_data, "override_library") and target_data.override_library is not None:
            raise RuntimeError(f"DataBlock {data_name} has override_library; cannot delete")
    except AttributeError:
        pass
    except Exception as dep_err:
        raise RuntimeError(f"Fail-closed: failed checking external dependencies on {data_name}: {dep_err}")


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _remove_authorized_stashed_datablock
# PURPOSE: 先执行授权与依赖核验再依次触发 BUG-11 前后故障注入窗口并执行 do_unlink=False 物理删除与删后存在性核验
# REASON: 将受权 DataBlock 删除入口迁入 Layer 3，保证物理删除不可绕过授权验证执行
def _remove_authorized_stashed_datablock(
    tx: Any,
    stashed: Dict[str, Any],
    matching_auth: Dict[str, Any],
    data_ptr: Any,
    data_name: Any,
    target_data: Any,
    target_coll: Any,
    *,
    trigger_fault_injection: Callable[..., None],
) -> None:
    """Validate and execute the original authorized DataBlock deletion."""
    _validate_stashed_datablock_delete_authority(
        tx,
        matching_auth,
        data_ptr,
        data_name,
        target_data,
        target_coll,
    )

    trigger_fault_injection(
        "during_cleanup_datablock_after_auth_before_remove",
        {
            "stashed": stashed,
            "data_ptr": data_ptr,
            "data": target_data,
            "tx": tx,
        },
    )

    target_coll.remove(target_data, do_unlink=False)

    trigger_fault_injection(
        "during_cleanup_datablock_after_remove_before_verify",
        {
            "stashed": stashed,
            "data_ptr": data_ptr,
            "tx": tx,
        },
    )

    still_present = False
    try:
        still_present = any(
            (data_ptr and item.as_pointer() == data_ptr)
            for item in target_coll
        )
    except Exception:
        still_present = True

    if still_present:
        raise RuntimeError(
            f"Failed to delete datablock {data_name}: still exists in {target_coll}"
        )
