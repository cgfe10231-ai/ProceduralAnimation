"""Authorized snapshot baseline relationship restoration migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-13)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-25T17:15:39+08:00]
# NODE: 10-B / L3-13
# FUNCTION: _authorized_restore_snapshot_collection_child
# PURPOSE: 核验原始存活父子 Collection 引用与指针后按快照恢复 Collection 层级边并进行 RNA 复核
# REASON: 将快照基线 Collection 层级恢复从 arm_ik.py 物理迁入 Layer 3，全部外部依赖经显式参数传入
def _authorized_restore_snapshot_collection_child(
    parent_ref: bpy.types.Collection,
    parent_ptr: int,
    child_ref: bpy.types.Collection,
    child_ptr: int,
    restoration_errors: List[str],
    *,
    find_live_collection_by_identity: Callable[..., Optional[bpy.types.Collection]],
    is_child_collection_linked_by_identity: Callable[..., bool],
) -> None:
    """Restore a baseline Collection hierarchy edge by original live identity."""
    parent = find_live_collection_by_identity(parent_ref, parent_ptr)
    child = find_live_collection_by_identity(child_ref, child_ptr)
    if parent is None or child is None:
        restoration_errors.append(
            f"Snapshot Collection hierarchy identity unproven: parent={parent_ptr}, child={child_ptr}"
        )
        return
    if is_child_collection_linked_by_identity(parent, child, child_ptr):
        return
    try:
        parent.children.link(child)
    except BaseException as exc:
        restoration_errors.append(
            f"Snapshot Collection hierarchy relink failed: {type(exc).__name__}: {exc}"
        )
        return
    if not is_child_collection_linked_by_identity(parent, child, child_ptr):
        restoration_errors.append(
            f"Snapshot Collection hierarchy relink not reflected in RNA: parent={parent_ptr}, child={child_ptr}"
        )


# [INTRODUCED 2026-11-25T17:15:39+08:00]
# NODE: 10-B / L3-13
# FUNCTION: _authorized_ensure_snapshot_collection_link
# PURPOSE: 核验存活 Collection 与 Object 身份后恢复快照中既有的成员绑定关系并执行 RNA 验证
# REASON: 将快照 Collection <-> Object 成员关系恢复从 arm_ik.py 物理迁入 Layer 3，全部外部依赖经显式参数传入
def _authorized_ensure_snapshot_collection_link(
    col: Optional[bpy.types.Collection],
    obj_ref: bpy.types.Object,
    obj_ptr: Optional[int],
    restoration_errors: List[str],
    *,
    find_live_collection_by_identity: Callable[..., Optional[bpy.types.Collection]],
    find_live_object_by_identity: Callable[..., Optional[bpy.types.Object]],
    is_object_linked_to_collection_by_identity: Callable[..., bool],
) -> None:
    """Layer 3 restoration of a pre-existing snapshot Collection <-> Object membership by verified identity."""
    if col is None:
        return
    try:
        col_ptr = col.as_pointer()
    except ReferenceError:
        restoration_errors.append("Snapshot collection reference destroyed before membership restoration")
        return

    live_col = find_live_collection_by_identity(col, col_ptr)
    if live_col is None:
        restoration_errors.append("Snapshot collection identity lost during membership restoration")
        return

    if obj_ptr is None:
        try:
            obj_ptr = obj_ref.as_pointer()
        except ReferenceError:
            restoration_errors.append("Snapshot member object destroyed before membership restoration")
            return

    live_obj = find_live_object_by_identity(obj_ref, obj_ptr)
    if live_obj is None:
        restoration_errors.append("Snapshot member object identity lost during membership restoration")
        return

    if not is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
        try:
            live_col.objects.link(live_obj)
        except BaseException as exc:
            restoration_errors.append(
                f"Snapshot Collection/Object membership restore failed (col={col_ptr}, obj={obj_ptr}): "
                f"{type(exc).__name__}: {exc}"
            )
            return
        if not is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
            restoration_errors.append(
                f"Snapshot Collection/Object membership restore did not take effect "
                f"(col={col_ptr}, obj={obj_ptr})"
            )


# [INTRODUCED 2026-11-25T17:15:39+08:00]
# NODE: 10-B / L3-13
# FUNCTION: _authorized_restore_collection_object_relationships
# PURPOSE: 按 ALL / PRE_CONTROLLER_REMOVE / POST_CONTROLLER_RESTORE 阶段协调关系日志逆向撤销及原始与暂存对象成员关系恢复
# REASON: 将两阶段 Collection <-> Object 关系恢复调度完整物理迁入 Layer 3，保持原兼容回调替换路径
def _authorized_restore_collection_object_relationships(
    active_tx: Optional[Any],
    snapshot: Dict[str, Any],
    restoration_errors: List[str],
    phase: str = "ALL",
    *,
    authorized_revert_relationship_record: Callable[[Dict[str, Any], Any, List[str]], None],
    find_live_collection_by_identity: Callable[..., Optional[bpy.types.Collection]],
    find_live_object_by_identity: Callable[..., Optional[bpy.types.Object]],
    is_object_linked_to_collection_by_identity: Callable[..., bool],
    verify_controller_object_transaction_authority: Callable[..., Optional[str]],
    authorized_ensure_snapshot_collection_link: Callable[..., None],
) -> None:
    """Layer 3 authoritative rollback and restoration of Collection <-> Object relationships."""
    if phase in ("ALL", "PRE_CONTROLLER_REMOVE") and active_tx is not None:
        logged_records = list(getattr(active_tx, "prepared_relationship_mutations", []))
        logged_link_pairs = set()
        for op_record in reversed(logged_records):
            if op_record.get("intended_mutation") == "COLLECTION_OBJECT_LINK":
                src_id = op_record.get("source_identity", {})
                tgt_id = op_record.get("target_identity", {})
                logged_link_pairs.add((src_id.get("ptr"), tgt_id.get("ptr")))
                authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

        # A legacy created_collection_links entry does NOT authorize destructive
        # unlink. Only an actual Layer 3 relationship operation may be undone.
        for link_rec in reversed(list(getattr(active_tx, "created_collection_links", []))):
            col_ref = link_rec.get("col_ref")
            col_ptr = link_rec.get("col_ptr")
            obj_ref = link_rec.get("obj_ref")
            obj_ptr = link_rec.get("obj_ptr")
            if (col_ptr, obj_ptr) in logged_link_pairs:
                continue
            live_col = find_live_collection_by_identity(col_ref, col_ptr)
            live_obj = find_live_object_by_identity(obj_ref, obj_ptr) if obj_ptr is not None else None
            if (live_col is not None and live_obj is not None
                    and is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)):
                restoration_errors.append(
                    f"Collection/Object rollback unauthorized without Layer 3 log: "
                    f"collection_ptr={col_ptr}, object_ptr={obj_ptr}; no unlink performed"
                )

    if phase in ("ALL", "POST_CONTROLLER_RESTORE"):
        if active_tx is not None:
            for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
                if op_record.get("intended_mutation") == "COLLECTION_OBJECT_UNLINK":
                    authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

        # Ensure pre-existing controller collection memberships from snapshot are intact by identity
        controllers_snap = snapshot.get("controllers", {})
        for c_name, c_snap in controllers_snap.items():
            if not c_snap.get("exists"):
                continue
            original_ref = c_snap.get("obj_ref")
            original_ptr = c_snap.get("obj_ptr")
            if original_ref is None or original_ptr is None:
                continue
            live_original = find_live_object_by_identity(original_ref, original_ptr)
            if live_original is None:
                continue
            if active_tx is not None and verify_controller_object_transaction_authority(
                live_original, active_tx,
            ) != 'SNAPSHOT_ORIGINAL':
                # Never restore memberships of merely observed external objects.
                continue
            col_refs = c_snap.get("collection_refs")
            col_ptrs = c_snap.get("collection_ptrs")
            if col_refs is not None and col_ptrs is not None and len(col_refs) == len(col_ptrs):
                for c_ref, c_ptr in zip(col_refs, col_ptrs):
                    live_col = find_live_collection_by_identity(c_ref, c_ptr)
                    if live_col is not None:
                        authorized_ensure_snapshot_collection_link(
                            live_col, live_original, original_ptr, restoration_errors
                        )
            else:
                if c_snap.get("collections"):
                    restoration_errors.append(
                        f"Controller '{c_name}' snapshot Collection identity metadata missing; "
                        "refusing membership restoration by name"
                    )

        # Ensure stashed objects' original collection memberships are intact by identity
        if active_tx is not None:
            for stashed in getattr(active_tx, "stashed_objects", []):
                obj = stashed.get("stashed_obj")
                obj_ptr = stashed.get("stashed_obj_ptr")
                live_stashed = find_live_object_by_identity(obj, obj_ptr) if (obj and obj_ptr) else obj
                if live_stashed is None:
                    continue
                s_col_refs = stashed.get("collection_refs")
                s_col_ptrs = stashed.get("collection_ptrs")
                if s_col_refs is not None and s_col_ptrs is not None and len(s_col_refs) == len(s_col_ptrs):
                    for c_ref, c_ptr in zip(s_col_refs, s_col_ptrs):
                        live_col = find_live_collection_by_identity(c_ref, c_ptr)
                        if live_col is not None:
                            authorized_ensure_snapshot_collection_link(
                                live_col, live_stashed, obj_ptr, restoration_errors
                            )
                else:
                    if stashed.get("collections"):
                        restoration_errors.append(
                            "Stashed object snapshot Collection identity metadata missing; "
                            "refusing membership restoration by name"
                        )


# [INTRODUCED 2026-11-25T17:15:39+08:00]
# NODE: 10-B / L3-13
# FUNCTION: _authorized_restore_snapshot_object_parent
# PURPOSE: 在证明原始 Object 与父级存活身份前提下恢复快照 parent 及 matrix_parent_inverse 并联合验证
# REASON: 将快照 Object Parent 恢复从 arm_ik.py 物理迁入 Layer 3，全部外部依赖经显式参数传入
def _authorized_restore_snapshot_object_parent(
    obj_ref: bpy.types.Object,
    obj_ptr: int,
    parent_ref: Optional[bpy.types.Object],
    parent_ptr: Optional[int],
    orig_inverse: Any,
    restoration_errors: List[str],
    *,
    find_live_object_by_identity: Callable[..., Optional[bpy.types.Object]],
    matrix_equals: Callable[..., bool],
) -> None:
    """Restore a snapshot parent relationship only with proved live identities."""
    live_obj = find_live_object_by_identity(obj_ref, obj_ptr)
    if live_obj is None or orig_inverse is None:
        restoration_errors.append("Snapshot object parent authority missing: original object/inverse unavailable")
        return
    if parent_ref is None:
        if parent_ptr is not None:
            restoration_errors.append("Snapshot object parent reference missing for recorded pointer")
            return
        live_parent = None
    else:
        if not isinstance(parent_ptr, int) or parent_ptr <= 0:
            restoration_errors.append("Snapshot object parent original pointer missing")
            return
        live_parent = find_live_object_by_identity(parent_ref, parent_ptr)
        if live_parent is None:
            restoration_errors.append("Snapshot object parent identity lost; refusing reparent")
            return
    try:
        current_parent = live_obj.parent
        current_ptr = current_parent.as_pointer() if current_parent is not None else None
        current_inv = live_obj.matrix_parent_inverse
        if (current_parent == live_parent and current_ptr == parent_ptr
                and matrix_equals(current_inv, orig_inverse)):
            return
        live_obj.parent = live_parent
        live_obj.matrix_parent_inverse = orig_inverse.copy()
        final_parent = live_obj.parent
        final_ptr = final_parent.as_pointer() if final_parent is not None else None
        if (final_parent != live_parent or final_ptr != parent_ptr
                or not matrix_equals(live_obj.matrix_parent_inverse, orig_inverse)):
            restoration_errors.append("Snapshot object parent restoration failed identity/inverse verification")
    except BaseException as exc:
        restoration_errors.append(
            f"Snapshot object parent restoration failed: {type(exc).__name__}: {exc}"
        )


# [INTRODUCED 2026-11-25T17:15:39+08:00]
# NODE: 10-B / L3-13
# FUNCTION: _authorized_restore_snapshot_constraint_targets_without_tx
# PURPOSE: 写入前完整核验双关系对存活身份后恢复快照 Constraint 目标对，并在失败时执行逆序补偿同时保留 BUG-07 错误记录
# REASON: 将 BUG-07 快照 Constraint 目标恢复与逆序补偿机制（含嵌套 target_matches）完整物理迁入 Layer 3
def _authorized_restore_snapshot_constraint_targets_without_tx(
    con: bpy.types.Constraint,
    sc: Dict[str, Any],
    bone_name: str,
    restoration_errors: List[str],
    *,
    find_live_object_by_identity: Callable[..., Optional[bpy.types.Object]],
) -> None:
    """Restore snapshot Constraint target pairs, refusing unproved Blender identities.

    All original target identities and BOTH field pairs are checked before writes.
    If a setter fails or verification fails, attempt a compensating restoration
    of the pre-call state and ALWAYS record a rollback error (never claim success).
    """
    label = f"{bone_name}/{sc.get('name', '<unknown>')}"
    planned = []
    previous = []

    def target_matches(current: Any, expected: Any, expected_ptr: Optional[int]) -> bool:
        if expected is None:
            return current is None and expected_ptr is None
        if current is None or type(expected_ptr) is not int or expected_ptr <= 0:
            return False
        try:
            return (current == expected
                    and int(current.as_pointer()) == expected_ptr
                    and find_live_object_by_identity(expected, expected_ptr) is not None)
        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
            return False

    try:
        original_con = sc.get("con_ref")
        original_con_ptr = sc.get("con_ptr")
        if (original_con is None or type(original_con_ptr) is not int
                or original_con_ptr <= 0 or con != original_con
                or int(con.as_pointer()) != original_con_ptr
                or int(original_con.as_pointer()) != original_con_ptr):
            raise RuntimeError("original Constraint identity mismatch")

        for field, subfield in (("target", "subtarget"), ("pole_target", "pole_subtarget")):
            has_target = hasattr(con, field)
            has_sub = hasattr(con, subfield)
            expected_target = sc.get(field)
            expected_sub = sc.get(subfield, "")
            ptr_key = f"{field}_ptr"
            if ptr_key not in sc:
                raise RuntimeError(f"snapshot lacks captured original pointer for {field}")
            expected_ptr = sc[ptr_key]
            if not isinstance(expected_sub, str):
                raise RuntimeError(f"{subfield} snapshot is not a string")
            if not has_target:
                if (has_sub or expected_target is not None or expected_ptr is not None
                        or expected_sub != ""):
                    raise RuntimeError(f"{field} unavailable but snapshot contains relationship")
                continue
            if not has_sub and expected_sub:
                raise RuntimeError(f"{subfield} property absent but snapshot is nonempty")
            if not target_matches(expected_target, expected_target, expected_ptr):
                raise RuntimeError(f"{field} original Object identity unproven/dead")
            current_target = getattr(con, field)
            current_ptr = None
            if current_target is not None:
                current_ptr = int(current_target.as_pointer())
                if (current_ptr <= 0
                        or find_live_object_by_identity(current_target, current_ptr) is None):
                    raise RuntimeError(f"{field} current Object identity unreadable/dead")
            current_sub = getattr(con, subfield) if has_sub else ""
            if not isinstance(current_sub, str):
                raise RuntimeError(f"{subfield} current value is not a string")
            planned.append((field, subfield, has_sub, expected_target, expected_ptr, expected_sub))
            previous.append((field, subfield, has_sub, current_target, current_ptr, current_sub))
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        restoration_errors.append(f"BUG-07 snapshot Constraint target authority denied [{label}]: {exc}")
        return

    if not planned:
        return

    try:
        for field, subfield, has_sub, expected_target, expected_ptr, expected_sub in planned:
            if not target_matches(getattr(con, field), expected_target, expected_ptr):
                setattr(con, field, expected_target)
            if has_sub and getattr(con, subfield) != expected_sub:
                setattr(con, subfield, expected_sub)

        for field, subfield, has_sub, expected_target, expected_ptr, expected_sub in planned:
            if not target_matches(getattr(con, field), expected_target, expected_ptr):
                raise RuntimeError(f"{field} RNA did not restore original pointer")
            if has_sub and getattr(con, subfield) != expected_sub:
                raise RuntimeError(f"{subfield} RNA did not restore original string")
    except BaseException as exc:
        # A pair of RNA setters is not physically atomic. Compensate any
        # partial writes back to the exact pre-call values, without hiding error.
        compensation_errors = []
        for field, subfield, has_sub, old_target, old_ptr, old_sub in reversed(previous):
            try:
                actual_target = getattr(con, field)
                if not target_matches(actual_target, old_target, old_ptr):
                    setattr(con, field, old_target)
                if has_sub and getattr(con, subfield) != old_sub:
                    setattr(con, subfield, old_sub)
                if not target_matches(getattr(con, field), old_target, old_ptr):
                    raise RuntimeError(f"{field} compensation RNA identity mismatch")
                if has_sub and getattr(con, subfield) != old_sub:
                    raise RuntimeError(f"{subfield} compensation RNA value mismatch")
            except BaseException as compensation_exc:
                compensation_errors.append(
                    f"{field}/{subfield}: {type(compensation_exc).__name__}: {compensation_exc}"
                )
        restoration_errors.append(
            f"BUG-07 snapshot Constraint targets restore failed [{label}]: "
            f"{type(exc).__name__}: {exc}; compensation="
            + ("OK" if not compensation_errors else "FAILED [" + "; ".join(compensation_errors) + "]")
        )
