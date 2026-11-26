"""Complete Arm Rig rollback executor migrated from `src/rig/arm_ik.py` (Task 10-B Layer 5 L5-03)."""

from typing import Any, Callable, Dict, List, Optional

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector


# [INTRODUCED 2026-11-25T00:24:00+08:00]
# NODE: 10-B / L5-03
# FUNCTION: _rollback_arm_rig_state
# PURPOSE: 执行原完整事务快照恢复链及资源恢复错误汇总
# REASON: 将 ACTIVE 与 COMMITTING 异常后的总体恢复执行主体归入 Layer 5，保留原操作顺序、授权依赖及 Coordinator 控制权
def _rollback_arm_rig_state(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
    *,
    active_transaction_stack: List[Any],
    managed_armature_identities: Dict[str, Any],
    transaction_state_cls: Any,
    relationship_operation_state_cls: Any,
    trigger_fault_injection: Callable[..., None],
    authorized_revert_relationship_record: Callable[..., Any],
    authorized_restore_collection_object_relationships: Callable[..., Any],
    controller_role_for_name: Callable[..., Any],
    find_live_object_by_identity: Callable[..., Any],
    verify_controller_object_transaction_authority: Callable[..., Any],
    controller_is_borrowed_by_other_armature: Callable[..., Any],
    verify_failed_isolation_controller_recovery_authority: Callable[..., Any],
    authorized_restore_snapshot_object_parent: Callable[..., Any],
    matrix_equals: Callable[..., Any],
    authorized_remove_constraint: Callable[..., Any],
    authorized_restore_snapshot_constraint_targets_without_tx: Callable[..., Any],
    find_live_collection_by_identity: Callable[..., Any],
    is_child_collection_linked_by_identity: Callable[..., Any],
    authorized_restore_snapshot_collection_child: Callable[..., Any],
    authorized_ensure_snapshot_collection_link: Callable[..., Any],
    depsgraph_update: Callable[[], None],
) -> None:
    """Restore the Arm IK rig state precisely to the recorded snapshot."""
    trigger_fault_injection(
        "during_rollback_execution",
        {"arm": arm, "snapshot": snapshot, "tx": active_tx},
    )
    restoration_errors: List[str] = []

    # Step 0: Authoritatively revert constraint target/pole target relationships FIRST,
    # before any transaction-created target controller objects are deleted.
    if active_tx is not None:
        for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
            if op_record.get("intended_mutation") in (
                "CONSTRAINT_TARGET_ASSIGN",
                "CONSTRAINT_POLE_TARGET_ASSIGN",
            ):
                authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

    # Step 0.5: Authoritatively revert Object Parent relationships before created controller objects are deleted
    if active_tx is not None:
        for op_record in reversed(list(getattr(active_tx, "prepared_relationship_mutations", []))):
            if op_record.get("intended_mutation") == "OBJECT_PARENT_ASSIGN":
                authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

    # Step 1: Controller cleanup, stashed object restoration, and transform restoration
    # 1.0a: Revert transaction-created Collection <-> Object links via Layer 3 before removing created controllers
    authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase="PRE_CONTROLLER_REMOVE",
    )

    # 1.0b: Remove only controllers proven created AFTER this transaction's
    # entry baseline. A forged or stale registry entry is never deletion authority.
    if active_tx is not None:
        if active_tx.arm is not arm or active_tx.snapshot is not snapshot:
            restoration_errors.append("Controller cleanup rejected: transaction/snapshot ownership mismatch")
        else:
            # Validate the entire creation ledger before ANY destructive write.
            # A missing or forged list record must not silently hide a live
            # transaction-created Object from rollback verification.
            registry = getattr(active_tx, 'created_controller_objects', None)
            receipts = getattr(active_tx, '_controller_creation_receipts', None)
            entry_ptrs = active_tx.entry_object_ptrs
            proof_errors: List[str] = []
            validated: Dict[int, Dict[str, Any]] = {}
            if not isinstance(registry, list) or not isinstance(receipts, dict):
                proof_errors.append('Created controller registry/receipt ledger is malformed')
            elif not isinstance(entry_ptrs, (set, frozenset)):
                proof_errors.append('Created controller entry-pointer baseline is unavailable')
            else:
                for record in registry:
                    if not isinstance(record, dict):
                        proof_errors.append('Created controller registry contains a non-dictionary record')
                        continue
                    obj_ref, obj_ptr = record.get('obj_ref'), record.get('obj_ptr')
                    if obj_ref is None or type(obj_ptr) is not int or obj_ptr <= 0:
                        proof_errors.append('Created controller registry entry has invalid identity fields')
                        continue
                    if obj_ptr in validated:
                        proof_errors.append(f'Duplicate created controller identity pointer {obj_ptr}')
                        continue
                    validated[obj_ptr] = record
                    if obj_ptr in entry_ptrs:
                        proof_errors.append(f'Created controller pointer {obj_ptr} existed at transaction entry')
                    if controller_role_for_name(record.get('created_name')) is None:
                        proof_errors.append(f'Created controller pointer {obj_ptr} lacks an original controller role')
                    receipt = receipts.get(obj_ptr)
                    if (not isinstance(receipt, tuple) or len(receipt) != 4
                            or receipt[0] is not obj_ref
                            or receipt[1] != active_tx.session_id
                            or receipt[2] != active_tx.tx_id
                            or receipt[3] is not active_tx._controller_receipt_seal):
                        proof_errors.append(f'Created controller pointer {obj_ptr} has no matching original receipt')
                if set(validated) != set(receipts):
                    proof_errors.append('Created controller registry and creation receipts diverged')
            if proof_errors:
                # Fail closed rather than partially deleting objects under an
                # inconsistent or incomplete transaction ownership ledger.
                restoration_errors.extend(proof_errors)
            else:
                for obj_ptr, record in validated.items():
                    obj_ref = record['obj_ref']
                    live_obj = find_live_object_by_identity(obj_ref, obj_ptr)
                    if live_obj is None:
                        # Do not substitute a new Blender Object sharing the name.
                        continue
                    if verify_controller_object_transaction_authority(
                        live_obj, active_tx, created_only=True,
                    ) != 'TX_CREATED':
                        restoration_errors.append(
                            f'Controller deletion refused: pointer {obj_ptr} lacks transaction creation authority'
                        )
                        continue
                    # A foreign Armature referring to a newly-created controller
                    # removes exclusive deletion rights. Keep that resource and
                    # surface an explicit rollback failure for Coordinator isolation.
                    role = controller_role_for_name(record['created_name'])
                    if controller_is_borrowed_by_other_armature(active_tx.arm, live_obj, role):
                        restoration_errors.append(
                            f'Controller deletion refused: pointer {obj_ptr} is referenced by another Armature'
                        )
                        continue
                    bpy.data.objects.remove(live_obj, do_unlink=True)
                    if find_live_object_by_identity(obj_ref, obj_ptr) is not None:
                        restoration_errors.append(
                            f'Transaction-created controller removal failed (pointer {obj_ptr})'
                        )

    controllers_snap = snapshot.get("controllers", {})
    for c_name, c_snap in controllers_snap.items():
        if not c_snap["exists"]:
            # If snapshot recorded controller did not exist, transaction-owned
            # controllers have already been cleaned up by identity above.
            # External same-name objects MUST NOT be deleted.
            continue

        original_ref = c_snap["obj_ref"]
        original_ptr = c_snap["obj_ptr"]
        original_name = c_snap["obj_name"]

        live_original = find_live_object_by_identity(
            original_ref,
            original_ptr,
        )

        if live_original is None:
            restoration_errors.append(
                f"Original controller identity lost: {original_name}"
            )
            continue
        controller_authorized = False
        if active_tx is None:
            controller_authorized = True
        elif active_tx.state in (transaction_state_cls.ACTIVE, transaction_state_cls.ROLLING_BACK):
            if verify_controller_object_transaction_authority(
                live_original, active_tx,
            ) == 'SNAPSHOT_ORIGINAL':
                controller_authorized = True
            else:
                # An unrelated same-name controller may have been observed by the
                # snapshot; observing is not authority to restore or reparent it.
                continue
        elif active_tx.state == transaction_state_cls.FAILED:
            auth_ok, auth_reason = verify_failed_isolation_controller_recovery_authority(
                arm=arm,
                obj=live_original,
                snapshot=snapshot,
                tx=active_tx,
                expected_role=controller_role_for_name(original_name),
            )
            if auth_ok:
                controller_authorized = True
            else:
                restoration_errors.append(
                    f"FAILED isolation controller recovery authority denied for '{original_name}': {auth_reason}"
                )
                continue
        else:
            restoration_errors.append(
                f"Controller recovery rejected: unsupported transaction state {active_tx.state!r} for '{original_name}'"
            )
            continue

        if not controller_authorized:
            continue

        name_owner = bpy.data.objects.get(original_name)

        if (
            name_owner is not None
            and name_owner != live_original
        ):
            restoration_errors.append(
                "Original controller name occupied by "
                f"another object: {original_name}"
            )
            continue

        if live_original.name != original_name:
            live_original.name = original_name

        # Check if parent was already restored via Layer 3 relationship record
        parent_restored_via_tx = False
        if active_tx is not None:
            for op_rec in getattr(active_tx, "prepared_relationship_mutations", []):
                if op_rec.get("intended_mutation") == "OBJECT_PARENT_ASSIGN":
                    if op_rec.get("controller_ptr") == original_ptr or op_rec.get("controller_ref") == live_original:
                        parent_restored_via_tx = True
                        break

        if not parent_restored_via_tx:
            authorized_restore_snapshot_object_parent(
                live_original, original_ptr, c_snap.get("parent"),
                c_snap.get("parent_ptr"), c_snap.get("matrix_parent_inverse"),
                restoration_errors,
            )
        else:
            # A logged rollback owns the undo: never overwrite it with a second
            # unlogged parent write. Check that it actually restored the snapshot.
            snap_parent = c_snap.get("parent")
            snap_parent_ptr = c_snap.get("parent_ptr")
            curr_parent = live_original.parent
            curr_ptr = curr_parent.as_pointer() if curr_parent is not None else None
            if (curr_parent != snap_parent or curr_ptr != snap_parent_ptr
                    or not matrix_equals(live_original.matrix_parent_inverse,
                                          c_snap.get("matrix_parent_inverse"))):
                restoration_errors.append(
                    f"Controller '{original_name}' logged parent rollback does not match snapshot"
                )

        live_original.rotation_mode = c_snap["rotation_mode"]
        live_original.location = c_snap["location"].copy()
        live_original.rotation_euler = c_snap["rotation_euler"].copy()
        live_original.rotation_quaternion = c_snap["rotation_quaternion"].copy()
        live_original.rotation_axis_angle = tuple(c_snap["rotation_axis_angle"])
        live_original.scale = c_snap["scale"].copy()
        if live_original.type == "EMPTY":
            if c_snap.get("empty_display_type") is not None:
                live_original.empty_display_type = c_snap["empty_display_type"]
            if c_snap.get("empty_display_size") is not None:
                live_original.empty_display_size = c_snap["empty_display_size"]

    # Also ensure any other stashed objects from active_tx have their names restored before re-linking
    if active_tx is not None:
        for stashed in getattr(active_tx, "stashed_objects", []):
            obj = stashed.get("stashed_obj")
            obj_ptr = stashed.get("stashed_obj_ptr")
            orig_name = stashed.get("original_name")
            live_stashed = find_live_object_by_identity(obj, obj_ptr) if (obj and obj_ptr) else obj
            if live_stashed is not None:
                if orig_name and live_stashed.name != orig_name:
                    name_owner = bpy.data.objects.get(orig_name)
                    if name_owner is None or name_owner == live_stashed:
                        live_stashed.name = orig_name

    # 1.1: Restore unlinked original Collection <-> Object memberships via Layer 3
    authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase="POST_CONTROLLER_RESTORE",
    )

    # Step 2: Pose bones and constraints restoration
    pose_bones_snap = snapshot.get("pose_bones", {}) if isinstance(snapshot, dict) else {}

    # [INTRODUCED 2026-11-16T19:15:00+08:00]
    # FUNCTION: _rollback_arm_rig_state
    # PURPOSE: Comprehensive pre-deletion ledger, receipt, PoseBone identity, and live constraint membership validation before any removal
    # REASON: Task 10-B fix-4 Round 1/2, close pre-check gaps on bone_name/PoseBone identity and live constraint membership to prevent partial deletion
    constraint_creation_audit_passed = True
    if active_tx is not None:
        proof_errors: List[str] = []

        # Snapshot identity and transaction ownership verification
        if (active_tx.arm is not arm or active_tx.snapshot is not snapshot
                or not isinstance(snapshot, dict) or not isinstance(pose_bones_snap, dict)):
            proof_errors.append("Constraint rollback rejected: transaction/snapshot ownership mismatch")
            constraint_creation_audit_passed = False

        created_constraints = getattr(active_tx, "created_constraints", None)
        receipts = getattr(active_tx, "_constraint_creation_receipts", None)

        # 1. 登记表结构合法
        if not isinstance(created_constraints, list):
            proof_errors.append("Constraint rollback rejected: created_constraints registry is not a list")
            constraint_creation_audit_passed = False

        # 2. 凭据表结构合法
        if not isinstance(receipts, dict):
            proof_errors.append("Constraint rollback rejected: _constraint_creation_receipts is not a dict")
            constraint_creation_audit_passed = False

        if constraint_creation_audit_passed:
            if created_constraints or receipts:
                if active_tx.state != transaction_state_cls.ROLLING_BACK:
                    proof_errors.append(
                        f"Constraint rollback rejected: transaction state is {active_tx.state}, expected ROLLING_BACK"
                    )
                if not active_transaction_stack or active_tx not in active_transaction_stack:
                    proof_errors.append(
                        "Constraint rollback rejected: transaction does not belong to active transaction stack"
                    )

            # 3. 无重复资源身份 & 登记表记录合法
            reg_ptrs: List[int] = []
            reg_refs: List[Any] = []
            for rec in created_constraints:
                if not isinstance(rec, dict):
                    proof_errors.append("Constraint rollback rejected: registry record is not a dict")
                    continue
                c_ptr = rec.get("con_ptr")
                c_ref = rec.get("con_ref")
                pbone_ref = rec.get("pbone")
                b_name_rec = rec.get("bone_name")
                if (c_ref is None or type(c_ptr) is not int or c_ptr <= 0
                        or pbone_ref is None or not isinstance(b_name_rec, str) or not b_name_rec):
                    proof_errors.append(f"Constraint rollback rejected: invalid registry entry fields (ptr={c_ptr})")
                    continue
                if c_ptr in reg_ptrs or any(r == c_ref for r in reg_refs):
                    proof_errors.append(f"Constraint rollback rejected: duplicate constraint identity (ptr={c_ptr}) in registry")
                else:
                    reg_ptrs.append(c_ptr)
                    reg_refs.append(c_ref)

            rc_ptrs: List[int] = []
            for k in receipts.keys():
                if type(k) is not int or k <= 0:
                    proof_errors.append(f"Constraint rollback rejected: invalid receipt key {k}")
                    continue
                if k in rc_ptrs:
                    proof_errors.append(f"Constraint rollback rejected: duplicate receipt pointer {k}")
                else:
                    rc_ptrs.append(k)

            # 4. 登记表和凭据表指针集合完全一致
            set_reg_ptrs = set(reg_ptrs)
            set_rc_ptrs = set(rc_ptrs)
            if set_reg_ptrs != set_rc_ptrs:
                proof_errors.append(
                    f"Constraint rollback rejected: pointer mismatch between registry and receipts: "
                    f"registry_only={set_reg_ptrs - set_rc_ptrs}, receipts_only={set_rc_ptrs - set_reg_ptrs}"
                )

            # Collect all snapshot original constraint pointers and refs
            all_snapshot_con_ptrs = set()
            all_snapshot_con_refs = set()
            for b_name_s, b_data_s in pose_bones_snap.items():
                if isinstance(b_data_s, dict):
                    for sc in b_data_s.get("constraints", []):
                        if isinstance(sc, dict):
                            if sc.get("con_ptr") is not None:
                                all_snapshot_con_ptrs.add(sc["con_ptr"])
                            if sc.get("con_ref") is not None:
                                all_snapshot_con_refs.add(sc["con_ref"])

            # 5. 逐一验证每份凭据、PoseBone 实时身份与当前约束集合归属
            seal = getattr(active_tx, "_constraint_receipt_seal", None)
            for rec in created_constraints:
                if not isinstance(rec, dict):
                    continue
                c_ptr = rec.get("con_ptr")
                c_ref = rec.get("con_ref")
                rec_pbone = rec.get("pbone")
                rec_bone_name = rec.get("bone_name")

                # 核验登记 bone_name 与所属 PoseBone 实时身份一致
                live_pbone = None
                if not isinstance(rec_bone_name, str) or not rec_bone_name:
                    proof_errors.append(f"Constraint rollback rejected: invalid bone_name for ptr={c_ptr}")
                elif rec_bone_name not in pose_bones_snap:
                    proof_errors.append(
                        f"Constraint rollback rejected: registered bone_name '{rec_bone_name}' not in snapshot for ptr={c_ptr}"
                    )
                elif arm is None or getattr(arm, "pose", None) is None or getattr(arm.pose, "bones", None) is None:
                    proof_errors.append(f"Constraint rollback rejected: armature pose bones unavailable for ptr={c_ptr}")
                else:
                    live_pbone = arm.pose.bones.get(rec_bone_name)
                    if live_pbone is None:
                        proof_errors.append(
                            f"Constraint rollback rejected: PoseBone '{rec_bone_name}' not found on armature for ptr={c_ptr}"
                        )
                    elif rec_pbone is None or live_pbone != rec_pbone:
                        proof_errors.append(
                            f"Constraint rollback rejected: PoseBone reference mismatch for bone '{rec_bone_name}' (ptr={c_ptr})"
                        )
                    else:
                        try:
                            if getattr(rec_pbone, "name", None) != rec_bone_name:
                                proof_errors.append(
                                    f"Constraint rollback rejected: PoseBone live name '{getattr(rec_pbone, 'name', None)}' != registered bone_name '{rec_bone_name}' (ptr={c_ptr})"
                                )
                        except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                            proof_errors.append(f"Constraint rollback rejected: PoseBone reference dead when reading name for ptr={c_ptr}")

                if c_ptr not in receipts:
                    proof_errors.append(f"Constraint rollback rejected: missing receipt for registered constraint ptr={c_ptr}")
                    continue

                rc = receipts[c_ptr]
                # 每份凭据均为长度恰好为 8 的元组
                if not isinstance(rc, tuple) or len(rc) != 8:
                    proof_errors.append(f"Constraint rollback rejected: receipt for ptr={c_ptr} is not an 8-tuple")
                    continue

                rc_con, rc_con_ptr, rc_pbone, rc_pbone_ptr, rc_session_id, rc_tx_id, rc_seal, rc_before_ptrs = rc

                # Constraint 引用、指针一致
                if rc_con is None or rc_con != c_ref or rc_con_ptr != c_ptr:
                    proof_errors.append(f"Constraint rollback rejected: receipt constraint mismatch for ptr={c_ptr}")
                else:
                    try:
                        if int(rc_con.as_pointer()) != c_ptr:
                            proof_errors.append(f"Constraint rollback rejected: live constraint pointer mismatch for ptr={c_ptr}")
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                        proof_errors.append(f"Constraint rollback rejected: constraint reference dead for ptr={c_ptr}")

                # PoseBone 引用、指针一致
                if rc_pbone is None or rc_pbone != rec_pbone or (live_pbone is not None and rc_pbone != live_pbone):
                    proof_errors.append(f"Constraint rollback rejected: receipt pose bone reference mismatch for ptr={c_ptr}")
                elif type(rc_pbone_ptr) is not int or rc_pbone_ptr <= 0:
                    proof_errors.append(f"Constraint rollback rejected: receipt pose bone pointer invalid for ptr={c_ptr}")
                else:
                    try:
                        live_pb_ptr = int(rc_pbone.as_pointer())
                        if live_pb_ptr != rc_pbone_ptr:
                            proof_errors.append(f"Constraint rollback rejected: live pose bone pointer mismatch for ptr={c_ptr}")
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                        proof_errors.append(f"Constraint rollback rejected: pose bone dead for ptr={c_ptr}")

                # 核验 Constraint 引用和指针确实存在于登记的 PoseBone 当前约束集合
                if rec_pbone is not None and c_ref is not None and type(c_ptr) is int and c_ptr > 0:
                    try:
                        bone_cons = list(rec_pbone.constraints)
                        matched_cands = []
                        cand_mismatch = False
                        for cand in bone_cons:
                            cand_ptr = int(cand.as_pointer())
                            if cand_ptr == c_ptr or cand == c_ref:
                                if cand_ptr != c_ptr or cand != c_ref:
                                    cand_mismatch = True
                                matched_cands.append(cand)
                        if cand_mismatch or len(matched_cands) != 1:
                            proof_errors.append(
                                f"Constraint rollback rejected: constraint ptr={c_ptr} not uniquely present on PoseBone '{rec_bone_name}'"
                            )
                    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError):
                        proof_errors.append(
                            f"Constraint rollback rejected: failed to enumerate constraints on PoseBone '{rec_bone_name}' for ptr={c_ptr}"
                        )

                # Session ID 一致
                if rc_session_id != active_tx.session_id:
                    proof_errors.append(f"Constraint rollback rejected: session_id mismatch for ptr={c_ptr}")

                # Transaction ID 一致
                if rc_tx_id != active_tx.tx_id:
                    proof_errors.append(f"Constraint rollback rejected: tx_id mismatch for ptr={c_ptr}")

                # Seal 一致
                if rc_seal is not seal or seal is None:
                    proof_errors.append(f"Constraint rollback rejected: seal mismatch for ptr={c_ptr}")

                # 创建前基线为 frozenset
                if not isinstance(rc_before_ptrs, frozenset):
                    proof_errors.append(f"Constraint rollback rejected: before_ptrs not frozenset for ptr={c_ptr}")
                elif c_ptr in rc_before_ptrs:
                    # Constraint 不属于创建前基线
                    proof_errors.append(f"Constraint rollback rejected: constraint ptr={c_ptr} in before_ptrs")

                # Constraint 不属于事务 Snapshot 原始资源
                if c_ptr in all_snapshot_con_ptrs or c_ref in all_snapshot_con_refs:
                    proof_errors.append(f"Constraint rollback rejected: constraint ptr={c_ptr} is snapshot original")

        if proof_errors:
            constraint_creation_audit_passed = False
            restoration_errors.extend(proof_errors)

    for b_name, b_snap in pose_bones_snap.items():
        pbone = arm.pose.bones.get(b_name)
        if pbone is None:
            continue

        pbone.rotation_mode = b_snap["rotation_mode"]
        pbone.location = b_snap["location"].copy()
        pbone.rotation_euler = b_snap["rotation_euler"].copy()
        pbone.rotation_quaternion = b_snap["rotation_quaternion"].copy()
        pbone.rotation_axis_angle = tuple(b_snap["rotation_axis_angle"])
        pbone.scale = b_snap["scale"].copy()
        pbone.matrix_basis = b_snap["matrix_basis"].copy()

        pbone.lock_ik_x = b_snap["lock_ik_x"]
        pbone.lock_ik_y = b_snap["lock_ik_y"]
        pbone.lock_ik_z = b_snap["lock_ik_z"]
        pbone.use_ik_limit_x = b_snap["use_ik_limit_x"]
        pbone.use_ik_limit_y = b_snap["use_ik_limit_y"]
        pbone.use_ik_limit_z = b_snap["use_ik_limit_z"]
        pbone.ik_min_x = b_snap["ik_min_x"]
        pbone.ik_max_x = b_snap["ik_max_x"]
        pbone.ik_min_y = b_snap["ik_min_y"]
        pbone.ik_max_y = b_snap["ik_max_y"]
        pbone.ik_min_z = b_snap["ik_min_z"]
        pbone.ik_max_z = b_snap["ik_max_z"]

        # Constraints non-destructive restoration
        saved_cons = b_snap.get("constraints", [])
        saved_con_refs = {sc["con_ref"] for sc in saved_cons if "con_ref" in sc}

        # 2.1: Remove ONLY constraints explicitly registered as created by this transaction via Layer 3
        if active_tx is not None and constraint_creation_audit_passed:
            for reg_con in list(getattr(active_tx, "created_constraints", [])):
                if reg_con.get("bone_name") == b_name or reg_con.get("pbone") == pbone:
                    try:
                        authorized_remove_constraint(
                            pbone,
                            reg_con,
                            phase="ROLLBACK",
                            active_tx=active_tx,
                        )
                    except Exception as ce:
                        restoration_errors.append(
                            f"Failed to remove transaction-created constraint '{reg_con.get('created_name')}': {ce}"
                        )

        # 2.2: Restore names and mutes for any stashed constraints on this bone
        if active_tx is not None:
            for item in getattr(active_tx, "stashed_constraints", []):
                if item["pbone"] == pbone:
                    c = item["con"]
                    if c in pbone.constraints.values():
                        c.name = item["orig_name"]
                        c.mute = item["orig_mute"]

        # 2.3: Reconcile and restore all saved constraints
        for sc in saved_cons:
            # Task 10-B-6
            # Resolve original constraint without substitution

            original_con = sc.get("con_ref")
            original_ptr = sc.get("con_ptr")

            if original_con is None or original_ptr is None:
                restoration_errors.append(
                    f"Missing snapshot identity: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            try:
                live_ptr = original_con.as_pointer()
            except ReferenceError:
                restoration_errors.append(
                    f"Original constraint destroyed: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            if live_ptr != original_ptr:
                restoration_errors.append(
                    f"Original constraint pointer changed: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            con = None

            for candidate in pbone.constraints:
                if candidate.as_pointer() == original_ptr:
                    con = candidate
                    break

            if con is None:
                restoration_errors.append(
                    f"Original constraint absent from live chain: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            if con.type != sc["type"]:
                restoration_errors.append(
                    f"Original constraint type mismatch: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            con.name = sc["name"]

            con.influence = sc["influence"]
            con.mute = sc["mute"]

            for prop, val in sc.get("generic_props", {}).items():
                if prop in ("target", "pole_target", "subtarget", "pole_subtarget"):
                    continue
                try:
                    trigger_fault_injection("during_constraint_property_restore", {
                        "bone": b_name, "con": sc["name"], "prop": prop, "val": val
                    })
                    if hasattr(con, prop):
                        if isinstance(val, (Vector, Euler, Quaternion, Matrix)):
                            setattr(con, prop, val.copy())
                        elif isinstance(val, tuple):
                            curr_val = getattr(con, prop)
                            if hasattr(curr_val, "__len__"):
                                for arr_i, el in enumerate(val):
                                    curr_val[arr_i] = el
                            else:
                                setattr(con, prop, val)
                        else:
                            setattr(con, prop, val)
                except Exception as ce:
                    restoration_errors.append(
                        f"Failed to restore property '{prop}' on constraint '{sc['name']}' "
                        f"on bone '{b_name}' with value {val!r}: {ce}"
                    )

            if active_tx is None:
                authorized_restore_snapshot_constraint_targets_without_tx(
                    con, sc, b_name, restoration_errors,
                )
            else:
                # When active_tx is present, verify targets match snapshot after Step 0 reversion
                if hasattr(con, "target") and con.target != sc.get("target"):
                    restoration_errors.append(
                        f"Constraint '{con.name}' target does not match snapshot after rollback: "
                        f"{con.target} != {sc.get('target')}"
                    )
                if hasattr(con, "subtarget") and con.subtarget != sc.get("subtarget", ""):
                    restoration_errors.append(
                        f"Constraint '{con.name}' subtarget does not match snapshot after rollback: "
                        f"'{con.subtarget}' != '{sc.get('subtarget', '')}'"
                    )
                if hasattr(con, "pole_target") and con.pole_target != sc.get("pole_target"):
                    restoration_errors.append(
                        f"Constraint '{con.name}' pole_target does not match snapshot after rollback: "
                        f"{con.pole_target} != {sc.get('pole_target')}"
                    )
                if hasattr(con, "pole_subtarget") and con.pole_subtarget != sc.get("pole_subtarget", ""):
                    restoration_errors.append(
                        f"Constraint '{con.name}' pole_subtarget does not match snapshot after rollback: "
                        f"'{con.pole_subtarget}' != '{sc.get('pole_subtarget', '')}'"
                    )

            if sc["type"] == "IK":
                con.chain_count = sc.get("chain_count", 0)
                con.use_tail = sc.get("use_tail", True)
                con.use_stretch = sc.get("use_stretch", False)
                con.pole_angle = sc.get("pole_angle", 0.0)
                con.iterations = sc.get("iterations", 500)
            elif sc["type"] == "COPY_ROTATION":
                con.target_space = sc.get("target_space", "WORLD")
                con.owner_space = sc.get("owner_space", "WORLD")
                con.mix_mode = sc.get("mix_mode", "REPLACE")
                con.use_x = sc.get("use_x", True)
                con.use_y = sc.get("use_y", True)
                con.use_z = sc.get("use_z", True)
                con.invert_x = sc.get("invert_x", False)
                con.invert_y = sc.get("invert_y", False)
                con.invert_z = sc.get("invert_z", False)
                con.use_offset = sc.get("use_offset", False)

        # 2.4: Restore relative ordering of original constraints by identity
        saved_ptrs = [sc["con_ptr"] for sc in saved_cons if sc.get("con_ptr")]
        live_ptr_to_idx = {c.as_pointer(): idx for idx, c in enumerate(pbone.constraints)}
        for i in range(len(saved_ptrs)):
            for j in range(i + 1, len(saved_ptrs)):
                ptr_i = saved_ptrs[i]
                ptr_j = saved_ptrs[j]
                if ptr_i in live_ptr_to_idx and ptr_j in live_ptr_to_idx:
                    idx_i = live_ptr_to_idx[ptr_i]
                    idx_j = live_ptr_to_idx[ptr_j]
                    if idx_i > idx_j:
                        pbone.constraints.move(idx_i, idx_j)
                        live_ptr_to_idx = {c.as_pointer(): idx for idx, c in enumerate(pbone.constraints)}

    # Step 3: Collection hierarchy rollback. Both relationship undo and
    # collection deletion must prove the same creation ownership.
    # Validate the ENTIRE receipt ledger before the first Collection mutation:
    # rejecting one forged entry must not leave earlier entries partly deleted.
    verified_created_collections = {}
    collection_rollback_authorized = active_tx is not None
    if active_tx is not None:
        try:
            registered = getattr(active_tx, "created_collections", None)
            receipts = getattr(active_tx, "_collection_creation_receipts", None)
            entry_ptrs = getattr(active_tx, "entry_collection_ptrs", None)
            session = getattr(active_tx, "session_record", None)
            if not isinstance(registered, list) or not isinstance(receipts, dict):
                raise RuntimeError("Collection registry/receipt ledger unavailable")
            if not isinstance(entry_ptrs, (set, frozenset)):
                raise RuntimeError("Collection entry baseline unavailable")
            if (session is None
                    or getattr(active_tx, "session_id", None) is None
                    or managed_armature_identities.get(active_tx.session_id) is not session
                    or session.original_blender_ref is not active_tx.arm):
                raise RuntimeError("Collection transaction session identity mismatch")
            for rec in registered:
                if not isinstance(rec, dict):
                    raise RuntimeError("Non-dictionary created Collection record")
                col_ptr = rec.get("col_ptr")
                col_ref = rec.get("col_ref")
                parent_ref = rec.get("initial_parent")
                parent_ptr = rec.get("initial_parent_ptr")
                if (not isinstance(col_ptr, int) or col_ptr <= 0
                        or not isinstance(parent_ptr, int) or parent_ptr <= 0
                        or col_ptr in entry_ptrs
                        or col_ptr in verified_created_collections
                        or col_ref is None or parent_ref is None):
                    raise RuntimeError(f"Invalid/duplicate Collection identity: {col_ptr!r}")
                receipt = receipts.get(col_ptr)
                if (not isinstance(receipt, tuple) or len(receipt) != 5
                        or receipt[0] != col_ref
                        or receipt[1] != parent_ref
                        or receipt[2] != active_tx.session_id
                        or receipt[3] != active_tx.tx_id
                        or receipt[4] is not active_tx._collection_receipt_seal):
                    raise RuntimeError(f"Collection creation receipt mismatch: {col_ptr}")
                try:
                    live_col_ptr = int(col_ref.as_pointer())
                    live_parent_ptr = int(parent_ref.as_pointer())
                except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                    raise RuntimeError(f"Collection/parent identity unreadable: {col_ptr}") from exc
                if (live_col_ptr != col_ptr or live_parent_ptr != parent_ptr
                        or find_live_collection_by_identity(col_ref, col_ptr) is None
                        or find_live_collection_by_identity(parent_ref, parent_ptr) is None):
                    raise RuntimeError(f"Collection/parent is not the originally registered live identity: {col_ptr}")
                verified_created_collections[col_ptr] = (col_ref, parent_ref, parent_ptr, receipt)
            if set(verified_created_collections) != set(receipts):
                raise RuntimeError("Collection registry and receipt ledger do not have identical identities")
        except Exception as exc:
            collection_rollback_authorized = False
            restoration_errors.append(
                f"COLLECTION_ROLLBACK_AUTHORITY_UNPROVEN: {exc}; refusing all Collection child undo/deletion"
            )

    # 3.0: Revert only the relationship edges authorized at creation.
    # NO_EFFECT, PREPARED and REVERTED contain no outstanding C-API undo.
    if active_tx is not None and collection_rollback_authorized:
        relationship_ops = getattr(active_tx, "prepared_relationship_mutations", [])
        for op_record in reversed(list(relationship_ops)):
            mutation = op_record.get("intended_mutation")
            if mutation not in ("COLLECTION_CHILD_LINK", "COLLECTION_CHILD_UNLINK"):
                continue
            state = op_record.get("operation_state")
            if state in (
                relationship_operation_state_cls.NO_EFFECT,
                relationship_operation_state_cls.REVERTED,
                relationship_operation_state_cls.PREPARED,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            ):
                authorized_revert_relationship_record(op_record, active_tx, restoration_errors)
                continue
            orig_rel = op_record.get("original_relationship_state")
            parent_ptr = op_record.get("parent_col_ptr")
            child_ptr = op_record.get("child_col_ptr")
            parent_ref = op_record.get("parent_col_ref")
            child_ref = op_record.get("child_col_ref")
            owned = verified_created_collections.get(child_ptr)
            valid_edge = (
                isinstance(orig_rel, dict)
                and owned is not None
                and owned[0] == child_ref
                and owned[1] == parent_ref
                and owned[2] == parent_ptr
                and find_live_collection_by_identity(parent_ref, parent_ptr) is not None
                and find_live_collection_by_identity(child_ref, child_ptr) is not None
            )
            if mutation == "COLLECTION_CHILD_LINK":
                valid_edge = (
                    valid_edge and orig_rel.get("linked") is False
                    and orig_rel.get("category") == "TX_ADDED"
                )
            else:
                prior_link = any(
                    isinstance(previous, dict)
                    and previous.get("intended_mutation") == "COLLECTION_CHILD_LINK"
                    and previous.get("parent_col_ptr") == parent_ptr
                    and previous.get("child_col_ptr") == child_ptr
                    and previous.get("parent_col_ref") == parent_ref
                    and previous.get("child_col_ref") == child_ref
                    and isinstance(previous.get("original_relationship_state"), dict)
                    and previous["original_relationship_state"].get("linked") is False
                    and previous["original_relationship_state"].get("category") == "TX_ADDED"
                    and previous.get("operation_state") in (
                        relationship_operation_state_cls.APPLIED_VERIFIED,
                        relationship_operation_state_cls.CONFIRMED,
                        relationship_operation_state_cls.REVERTED,
                    )
                    for previous in relationship_ops
                )
                valid_edge = (
                    valid_edge and orig_rel.get("linked") is True
                    and orig_rel.get("category") == "TX_UNLINKED_ORIGINAL"
                    and prior_link
                )
            if not valid_edge:
                restoration_errors.append(
                    f"COLLECTION_RELATION_ROLLBACK_AUTHORITY_UNPROVEN: "
                    f"{op_record.get('operation_id', '<unknown>')}; refusing relationship undo"
                )
                active_tx.update_relationship_mutation_state(
                    op_record, relationship_operation_state_cls.RECOVERY_UNCERTAIN,
                )
                continue
            authorized_revert_relationship_record(op_record, active_tx, restoration_errors)

    # 3.1: Delete only receipt-verified collections with NO remaining owners,
    # members, children, parents or Blender users. Never unlink a parent as a
    # side effect of deletion: an unexpected parent edge is external ownership.
    if active_tx is not None and collection_rollback_authorized:
        for col_ptr, (col_ref, parent_ref, parent_ptr, original_receipt) in verified_created_collections.items():
            target_col = find_live_collection_by_identity(col_ref, col_ptr)
            if target_col is None:
                restoration_errors.append(
                    f"Verified transaction Collection ptr={col_ptr} was destroyed before rollback deletion"
                )
                continue
            try:
                member_count = len(target_col.objects)
                child_count = len(target_col.children)
                parent_count = sum(
                    1 for p in bpy.data.collections
                    if p != target_col and is_child_collection_linked_by_identity(p, target_col, col_ptr)
                ) + sum(
                    1 for scene in bpy.data.scenes
                    if (getattr(scene, "collection", None) is not None
                        and is_child_collection_linked_by_identity(scene.collection, target_col, col_ptr))
                )
                user_count = int(target_col.users)
            except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                restoration_errors.append(
                    f"Cannot inspect verified Collection ptr={col_ptr} dependencies: {exc}"
                )
                continue
            if member_count or child_count or parent_count or user_count:
                restoration_errors.append(
                    f"Verified Collection ptr={col_ptr} still has dependencies "
                    f"(members={member_count}, children={child_count}, "
                    f"parents={parent_count}, users={user_count}); refusing deletion"
                )
                continue
            # Final revalidation immediately before destructive Blender call;
            # fault hooks in preceding relationship undo may have changed logs.
            final_records = [
                rec for rec in active_tx.created_collections
                if isinstance(rec, dict) and rec.get("col_ptr") == col_ptr
            ]
            latest_receipt = active_tx._collection_creation_receipts.get(col_ptr)
            if (find_live_collection_by_identity(col_ref, col_ptr) != target_col
                    or find_live_collection_by_identity(parent_ref, parent_ptr) is None
                    or col_ptr in active_tx.entry_collection_ptrs
                    or len(final_records) != 1
                    or final_records[0].get("col_ref") != col_ref
                    or final_records[0].get("initial_parent") != parent_ref
                    or final_records[0].get("initial_parent_ptr") != parent_ptr
                    or latest_receipt != original_receipt
                    or original_receipt[4] is not active_tx._collection_receipt_seal):
                restoration_errors.append(f"Collection ptr={col_ptr} identity/authority changed before deletion")
                continue
            try:
                bpy.data.collections.remove(target_col)
            except Exception as exc:
                restoration_errors.append(f"Failed to remove verified Collection ptr={col_ptr}: {exc}")
                continue
            if find_live_collection_by_identity(col_ref, col_ptr) is not None:
                restoration_errors.append(f"Verified Collection ptr={col_ptr} still exists after removal")

    char_col_snap = snapshot.get("character_collection", {})
    if not char_col_snap.get("existed", False):
        # Transaction-owned collections are handled
        # exclusively by active_tx.created_collections.
        #
        # Never delete a collection merely because
        # its name is "Character".
        pass
    else:
        # ------------------------------------------------------
        # Task 10-B-7
        # Identity-safe restoration of Character collection
        # ------------------------------------------------------
        orig_name = char_col_snap.get("name")
        col = char_col_snap.get("col_ref")
        original_ptr = char_col_snap.get("col_ptr")

        if col is None or original_ptr is None:
            restoration_errors.append(
                "Character collection snapshot identity missing"
            )
        else:
            try:
                live_ptr = col.as_pointer()
            except ReferenceError:
                restoration_errors.append(
                    "Original Character collection destroyed"
                )
            else:
                if (live_ptr != original_ptr
                        or find_live_collection_by_identity(col, original_ptr) is None):
                    restoration_errors.append(
                        "Character collection original live identity changed"
                    )
                else:
                    # Only snapshot-proven hierarchy edges may be restored.
                    if orig_name is not None and col.name != orig_name:
                        col.name = orig_name

                    if char_col_snap.get("children_of_scene", False):
                        scene = bpy.context.scene if bpy.context else None
                        if scene is None:
                            restoration_errors.append("Original scene root unavailable for Character collection")
                        else:
                            scene_root = scene.collection
                            authorized_restore_snapshot_collection_child(
                                scene_root, scene_root.as_pointer(), col, original_ptr,
                                restoration_errors,
                            )

                    expected_parents = char_col_snap.get("parent_refs", [])
                    expected_parent_ptrs = char_col_snap.get("parent_ptrs", [])
                    if len(expected_parents) != len(expected_parent_ptrs):
                        restoration_errors.append("Character parent snapshot refs/pointers length mismatch")
                    else:
                        for parent, parent_ptr in zip(expected_parents, expected_parent_ptrs):
                            authorized_restore_snapshot_collection_child(
                                parent, parent_ptr, col, original_ptr, restoration_errors,
                            )

                    expected_children = char_col_snap.get("child_refs", [])
                    expected_child_ptrs = char_col_snap.get("child_ptrs", [])
                    if len(expected_children) != len(expected_child_ptrs):
                        restoration_errors.append("Character child snapshot refs/pointers length mismatch")
                    else:
                        for child, child_ptr in zip(expected_children, expected_child_ptrs):
                            authorized_restore_snapshot_collection_child(
                                col, original_ptr, child, child_ptr, restoration_errors,
                            )

                    # Member Objects restoration by reference via Layer 3
                    expected_refs = char_col_snap.get(
                        "object_refs", []
                    )

                    for obj in expected_refs:
                        try:
                            obj_ptr = obj.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Character collection original member was destroyed"
                            )
                            continue

                        authorized_ensure_snapshot_collection_link(
                            col,
                            obj,
                            obj_ptr,
                            restoration_errors,
                        )

    depsgraph_update()

    if restoration_errors:
        raise RuntimeError("Rollback constraint restoration failed: " + "; ".join(restoration_errors))