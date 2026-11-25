"""Authorized relationship reversal operations migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-12)."""

from typing import Any, Callable, Dict, List, Optional


# [INTRODUCED 2026-11-25T17:00:03+08:00]
# NODE: 10-B / L3-12
# FUNCTION: _authorized_restore_relationship
# PURPOSE: 逆序遍历事务准备的关系变更记录并委托单条逆向撤销回调恢复受权关系
# REASON: 将批量受权关系逆向恢复入口从 arm_ik.py 物理迁入 Layer 3，保持原回调替换路径与签名兼容
def _authorized_restore_relationship(
    active_tx: Optional[Any],
    snapshot: Optional[Dict[str, Any]],
    restoration_errors: List[str],
    mutation_type: Optional[str] = None,
    *,
    authorized_revert_relationship_record: Callable[[Dict[str, Any], Any, List[str]], None],
) -> None:
    """Authoritatively revert and restore relationships via Layer 3 records."""
    if active_tx is None:
        return
    for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
        if mutation_type is None or op_record.get("intended_mutation") == mutation_type:
            authorized_revert_relationship_record(op_record, active_tx, restoration_errors)


# [INTRODUCED 2026-11-25T17:00:03+08:00]
# NODE: 10-B / L3-12
# FUNCTION: _authorized_revert_relationship_record
# PURPOSE: 对单条 7 状态关系操作记录执行原子逆向撤销与 RNA 复核，完整覆盖全部 7 种关系变更分支
# REASON: 将完整单条关系逆向撤销实现从 arm_ik.py 物理迁入 Layer 3，禁止拆分或重构控制流，全部外部依赖经显式参数动态传入
def _authorized_revert_relationship_record(
    op_record: Dict[str, Any],
    active_tx: Any,
    restoration_errors: List[str],
    *,
    relationship_operation_state_cls: Any,
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    find_live_object_by_identity: Callable[..., Any],
    classify_constraint_target_pair_effect: Callable[..., Any],
    matrix_equals: Callable[..., bool],
    find_live_collection_by_identity: Callable[..., Any],
    is_child_collection_linked_by_identity: Callable[..., bool],
    is_object_linked_to_collection_by_identity: Callable[..., bool],
    bpy_module: Any,
    matrix_cls: Any,
) -> None:
    """Layer 3 atomic reversal of a single relationship operation record."""
    op_id = op_record.get("operation_id", "<unknown>")
    state = op_record.get("operation_state")

    if state in (relationship_operation_state_cls.NO_EFFECT, relationship_operation_state_cls.REVERTED):
        return

    if state == relationship_operation_state_cls.PREPARED:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.NO_EFFECT,
        )
        return

    if state == relationship_operation_state_cls.RECOVERY_UNCERTAIN:
        restoration_errors.append(
            f"Relationship rollback '{op_id}' remains RECOVERY_UNCERTAIN; refusing undo"
        )
        return

    try:
        trigger_fault_injection(
            "during_relationship_rollback_undo",
            {"op": op_record, "tx": active_tx},
        )
    except BaseException as exc:
        if op_record.get("operation_state") in (
            relationship_operation_state_cls.APPLYING,
            relationship_operation_state_cls.APPLIED_VERIFIED,
            relationship_operation_state_cls.CONFIRMED,
        ):
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
        # [INTRODUCED 2026-11-11T22:38:48+08:00]
        # FUNCTION: _authorized_revert_relationship_record
        # PURPOSE: Propagate RECOVERY_UNCERTAIN evidence or classify FAILED-C from verified relationship state
        # REASON: Task 10-B fix-2, TEST-127 / TEST-149
        if op_record.get("operation_state") == relationship_operation_state_cls.RECOVERY_UNCERTAIN:
            restoration_errors.append(
                f"Relationship rollback '{op_id}' fault (RECOVERY_UNCERTAIN): {type(exc).__name__}: {exc}"
            )
        else:
            restoration_errors.append(
                f"Relationship rollback '{op_id}' fault: {type(exc).__name__}: {exc}"
            )
        return

    src_id = op_record.get("source_identity", {})
    tgt_id = op_record.get("target_identity", {})
    orig_rel = op_record.get("original_relationship_state", {})
    category = orig_rel.get("category", "OWNERSHIP_UNKNOWN")
    mutation = op_record.get("intended_mutation")

    if mutation in ("CONSTRAINT_TARGET_ASSIGN", "CONSTRAINT_POLE_TARGET_ASSIGN"):
        field = op_record.get("field", "target" if mutation == "CONSTRAINT_TARGET_ASSIGN" else "pole_target")
        subtarget_field = op_record.get("subtarget_field", "subtarget" if mutation == "CONSTRAINT_TARGET_ASSIGN" else "pole_subtarget")

        pbone = op_record.get("pbone_ref", orig_rel.get("pbone_ref"))
        pbone_ptr = op_record.get("pbone_ptr", orig_rel.get("pbone_ptr"))
        con = op_record.get("con_ref", orig_rel.get("con_ref"))
        con_ptr = op_record.get("con_ptr", orig_rel.get("con_ptr"))

        orig_target = op_record.get("orig_target_ref", orig_rel.get("orig_target_ref"))
        orig_target_ptr = op_record.get("orig_target_ptr", orig_rel.get("orig_target_ptr"))
        orig_subtarget = op_record.get("orig_subtarget", orig_rel.get("orig_subtarget", ""))

        dest_target = op_record.get("dest_target_ref", orig_rel.get("dest_target_ref"))
        dest_target_ptr = op_record.get("dest_target_ptr", orig_rel.get("dest_target_ptr"))

        # Verify pbone and con identity
        con_alive = False
        if con is not None and con_ptr is not None:
            try:
                if con.as_pointer() == con_ptr:
                    con_alive = True
            except ReferenceError:
                con_alive = False

        if not con_alive:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Constraint identity lost during target relationship rollback for {mutation}")
            return

        # Verify orig_target identity if not None
        if orig_target is not None:
            try:
                live_target_ptr = orig_target.as_pointer()
                if orig_target_ptr is not None and live_target_ptr != orig_target_ptr:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original constraint target pointer changed during rollback")
                    return
                if find_live_object_by_identity(orig_target, orig_target_ptr) is None:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original constraint target object destroyed during rollback")
                    return
            except ReferenceError:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append("Original constraint target destroyed during rollback")
                return

        if state == relationship_operation_state_cls.APPLYING:
            # An interrupted two-field assignment can change only the target,
            # only the subtarget, or both. Never infer NO_EFFECT from the
            # target alone; preserve reversible partial writes.
            try:
                if "dest_subtarget" not in op_record and "dest_subtarget" not in orig_rel:
                    raise RuntimeError("Destination subtarget evidence missing")
                dest_subtarget = op_record.get("dest_subtarget", orig_rel.get("dest_subtarget"))
                curr_target = getattr(con, field, None)
                curr_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
                classification = classify_constraint_target_pair_effect(
                    curr_target, curr_sub,
                    orig_target, orig_target_ptr, orig_subtarget,
                    dest_target, dest_target_ptr, dest_subtarget,
                )
            except Exception as exc:
                active_tx.update_relationship_mutation_state(
                    op_record, relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(
                    f"Constraint target rollback '{op_id}' pair inspection failed: {type(exc).__name__}: {exc}"
                )
                return
            active_tx.update_relationship_mutation_state(op_record, classification)
            if classification == relationship_operation_state_cls.NO_EFFECT:
                return
            if classification == relationship_operation_state_cls.RECOVERY_UNCERTAIN:
                restoration_errors.append(
                    f"Constraint target rollback '{op_id}' observed unrecognized target/subtarget pair"
                )
                return
            state = relationship_operation_state_cls.APPLIED_VERIFIED

        if state not in (relationship_operation_state_cls.APPLIED_VERIFIED, relationship_operation_state_cls.CONFIRMED):
            restoration_errors.append(
                f"Relationship operation '{op_id}' in unexpected state '{state}' during target rollback"
            )
            return

        try:
            setattr(con, field, orig_target)
            if hasattr(con, subtarget_field):
                setattr(con, subtarget_field, orig_subtarget)

            rev_target = getattr(con, field, None)
            rev_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
            rev_target_ptr = rev_target.as_pointer() if (rev_target and hasattr(rev_target, "as_pointer")) else None

            tgt_matches = (rev_target == orig_target if orig_target is not None else rev_target is None)
            ptr_matches = (rev_target_ptr == orig_target_ptr)
            sub_matches = (rev_sub == orig_subtarget)

            if not (tgt_matches and ptr_matches and sub_matches):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(f"Failed to verify constraint {field} reversion")
                return
        except BaseException as be:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Exception during constraint {field} reversion: {be}")
            return

        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.REVERTED,
        )
        return

    elif mutation == "OBJECT_PARENT_ASSIGN":
        obj = op_record.get("controller_ref", orig_rel.get("controller_ref"))
        obj_ptr = op_record.get("controller_ptr", orig_rel.get("controller_ptr"))
        orig_parent = op_record.get("orig_parent_ref", orig_rel.get("orig_parent_ref"))
        orig_parent_ptr = op_record.get("orig_parent_ptr", orig_rel.get("orig_parent_ptr"))
        orig_parent_name = op_record.get("orig_parent_name", orig_rel.get("orig_parent_name"))
        orig_inv = op_record.get("orig_matrix_parent_inverse", orig_rel.get("orig_matrix_parent_inverse"))
        if orig_inv is None:
            orig_inv = matrix_cls.Identity(4)

        live_obj = find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if live_obj is None:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Controller identity lost during object parent rollback for '{op_id}'")
            return

        if state == relationship_operation_state_cls.APPLYING:
            curr_p = getattr(live_obj, "parent", None)
            curr_p_ptr = curr_p.as_pointer() if (curr_p is not None and hasattr(curr_p, "as_pointer")) else None
            curr_inv = getattr(live_obj, "matrix_parent_inverse", matrix_cls.Identity(4)).copy()

            p_changed = False
            if orig_parent is None and curr_p is not None:
                p_changed = True
            elif orig_parent is not None and (curr_p is None or curr_p != orig_parent or curr_p_ptr != orig_parent_ptr):
                p_changed = True

            inv_changed = not matrix_equals(orig_inv, curr_inv, tol=1e-5)
            if not p_changed and not inv_changed:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.NO_EFFECT,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.APPLIED_VERIFIED,
            )
            state = relationship_operation_state_cls.APPLIED_VERIFIED

        if state not in (relationship_operation_state_cls.APPLIED_VERIFIED, relationship_operation_state_cls.CONFIRMED):
            restoration_errors.append(
                f"Relationship operation '{op_id}' in unexpected state '{state}' during object parent rollback"
            )
            return

        live_parent = None
        if orig_parent is not None:
            try:
                if orig_parent_ptr is not None and orig_parent.as_pointer() != orig_parent_ptr:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original parent pointer changed during rollback")
                    return
                live_parent = find_live_object_by_identity(orig_parent, orig_parent_ptr)
                if live_parent is None:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append("Original parent object destroyed during rollback")
                    return
                if orig_parent_name and orig_parent_name in bpy_module.data.objects:
                    if bpy_module.data.objects[orig_parent_name] != live_parent:
                        active_tx.update_relationship_mutation_state(
                            op_record,
                            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                        )
                        restoration_errors.append(f"Original parent name '{orig_parent_name}' occupied by another object")
                        return
            except ReferenceError:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append("Original parent destroyed during rollback")
                return

        try:
            live_obj.parent = live_parent
            live_obj.matrix_parent_inverse = orig_inv.copy()
        except BaseException as be:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Exception during object parent reversion: {be}")
            return

        rev_p = getattr(live_obj, "parent", None)
        rev_inv = getattr(live_obj, "matrix_parent_inverse", matrix_cls.Identity(4))
        p_ok = (rev_p == live_parent)
        inv_ok = matrix_equals(rev_inv, orig_inv, tol=1e-5)
        if p_ok and inv_ok:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.REVERTED,
            )
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append("Object parent restoration RNA verification failed")
        return

    elif mutation in ("COLLECTION_CHILD_LINK", "COLLECTION_CHILD_UNLINK"):
        parent_col = op_record.get("parent_col_ref", orig_rel.get("parent_col_ref"))
        parent_ptr = op_record.get("parent_col_ptr", orig_rel.get("parent_col_ptr"))
        child_col = op_record.get("child_col_ref", orig_rel.get("child_col_ref"))
        child_ptr = op_record.get("child_col_ptr", orig_rel.get("child_col_ptr"))

        live_parent = find_live_collection_by_identity(parent_col, parent_ptr)
        live_child = find_live_collection_by_identity(child_col, child_ptr)

        if state == relationship_operation_state_cls.APPLYING:
            if live_parent is None or live_child is None:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                return
            is_linked = is_child_collection_linked_by_identity(live_parent, live_child, child_ptr)
            if mutation == "COLLECTION_CHILD_LINK":
                if not is_linked:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.NO_EFFECT,
                    )
                    return
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.APPLIED_VERIFIED,
                )
                state = relationship_operation_state_cls.APPLIED_VERIFIED
            else:
                if is_linked:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.NO_EFFECT,
                    )
                    return
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.APPLIED_VERIFIED,
                )
                state = relationship_operation_state_cls.APPLIED_VERIFIED

        if state not in (relationship_operation_state_cls.APPLIED_VERIFIED, relationship_operation_state_cls.CONFIRMED):
            restoration_errors.append(
                f"Relationship operation '{op_id}' in unexpected state '{state}' during collection child rollback"
            )
            return

        if live_parent is None or live_child is None:
            if mutation == "COLLECTION_CHILD_LINK" and not is_child_collection_linked_by_identity(parent_col, child_col, child_ptr):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.REVERTED,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append("Parent or child collection identity lost during collection child rollback")
            return

        if mutation == "COLLECTION_CHILD_LINK":
            if is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                try:
                    live_parent.children.unlink(live_child)
                except Exception as e:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append(f"Failed to unlink child collection '{live_child.name}': {e}")
                    return
            if not is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.REVERTED,
                )
            else:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(f"Child collection '{live_child.name}' still linked after unlink")
            return
        else:
            if not is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                try:
                    live_parent.children.link(live_child)
                except Exception as e:
                    active_tx.update_relationship_mutation_state(
                        op_record,
                        relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                    )
                    restoration_errors.append(f"Failed to relink child collection '{live_child.name}': {e}")
                    return
            if is_child_collection_linked_by_identity(live_parent, live_child, child_ptr):
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.REVERTED,
                )
            else:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                restoration_errors.append(f"Child collection '{live_child.name}' not linked after restoration")
            return

    col_ref = src_id.get("ref", op_record.get("source_reference"))
    col_ptr = src_id.get("ptr")
    obj_ref = tgt_id.get("ref", op_record.get("target_reference"))
    obj_ptr = tgt_id.get("ptr")

    live_col = find_live_collection_by_identity(col_ref, col_ptr)
    live_obj = find_live_object_by_identity(obj_ref, obj_ptr) if obj_ptr is not None else None

    if state == relationship_operation_state_cls.APPLYING:
        if live_col is None or live_obj is None or category == "OWNERSHIP_UNKNOWN":
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object APPLYING rollback '{op_id}' identity/ownership unproven")
            return

        is_linked = is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        if mutation == "COLLECTION_OBJECT_LINK":
            if not is_linked:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.NO_EFFECT,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.APPLIED_VERIFIED,
            )
            state = relationship_operation_state_cls.APPLIED_VERIFIED
        elif mutation == "COLLECTION_OBJECT_UNLINK":
            if is_linked:
                active_tx.update_relationship_mutation_state(
                    op_record,
                    relationship_operation_state_cls.NO_EFFECT,
                )
                return
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.APPLIED_VERIFIED,
            )
            state = relationship_operation_state_cls.APPLIED_VERIFIED
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            return

    if state not in (relationship_operation_state_cls.APPLIED_VERIFIED, relationship_operation_state_cls.CONFIRMED):
        restoration_errors.append(
            f"Relationship operation '{op_id}' in unexpected state '{state}' during rollback"
        )
        return

    if live_col is None or live_obj is None or category == "OWNERSHIP_UNKNOWN":
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        restoration_errors.append(f"Collection/Object rollback '{op_id}' identity or ownership unproven")
        return

    if mutation == "COLLECTION_OBJECT_LINK":
        if category != "TX_ADDED":
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object link rollback '{op_id}' lacks TX_ADDED authority")
            return
        try:
            if is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                live_col.objects.unlink(live_obj)
            still_linked = is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        except BaseException as exc:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object unlink rollback '{op_id}' failed: {type(exc).__name__}: {exc}")
            return

        if still_linked:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object link rollback '{op_id}' failed RNA unlink verification")
            return

        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.REVERTED,
        )
    elif mutation == "COLLECTION_OBJECT_UNLINK":
        if category != "TX_UNLINKED_ORIGINAL":
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object unlink rollback '{op_id}' lacks TX_UNLINKED_ORIGINAL authority")
            return
        try:
            if not is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr):
                live_col.objects.link(live_obj)
            now_linked = is_object_linked_to_collection_by_identity(live_col, live_obj, obj_ptr)
        except BaseException as exc:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object relink rollback '{op_id}' failed: {type(exc).__name__}: {exc}")
            return

        if not now_linked:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
            restoration_errors.append(f"Collection/Object unlink rollback '{op_id}' failed RNA relink verification")
            return

        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.REVERTED,
        )
    else:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        restoration_errors.append(f"Unknown relationship rollback mutation '{mutation}' for '{op_id}'")
