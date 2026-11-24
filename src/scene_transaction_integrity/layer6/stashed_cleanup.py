"""Post-commit stashed Constraint and Object cleanup coordination migrated from `src/rig/arm_ik.py` (Task 10-B Layer 6 L6-01)."""

from typing import Any, Callable, Dict, List, Optional


# [INTRODUCED 2026-11-24T15:56:00+08:00]
# NODE: 10-B / L6-01
# FUNCTION: _cleanup_stashed_constraints
# PURPOSE: 在提交后清理阶段遍历暂存约束队列，经受权删除入口移除后更新未清理约束进度并保留首次异常原因
# REASON: 将废弃 Constraint 清理循环迁入 Layer 6，保持共享删除入口位置、异常捕获范围及列表就地移除语义
def _cleanup_stashed_constraints(
    tx: Any,
    cleanup_failures: List[str],
    first_cause: Optional[BaseException],
    *,
    authorized_remove_constraint: Callable[..., Any],
) -> Optional[BaseException]:
    """Execute the existing stashed constraint cleanup pass."""
    for stashed_con in list(tx.uncleaned_stashed_constraints):
        try:
            pbone = stashed_con.get("pbone")
            authorized_remove_constraint(
                pbone=pbone,
                con_record_or_ref=stashed_con,
                phase="POST_COMMIT_CLEANUP",
                active_tx=tx,
            )
            tx.uncleaned_stashed_constraints.remove(stashed_con)
        except Exception as exc:
            if first_cause is None:
                first_cause = exc
            cleanup_failures.append(
                "Failed to clean up stashed constraint "
                f"{stashed_con.get('orig_name')}: {exc}"
            )

    return first_cause


# [INTRODUCED 2026-11-24T15:56:00+08:00]
# NODE: 10-B / L6-01
# FUNCTION: _cleanup_stashed_object
# PURPOSE: 执行单个暂存废弃 Object 的故障注入、受权删除核验协调及 obj_cleaned 进度与首次异常记录
# REASON: 将废弃 Object 清理调度迁入 Layer 6，委托 Layer 3 执行物理删除与缺席核验并保证 DataBlock 前置条件不变
def _cleanup_stashed_object(
    stashed: Dict[str, Any],
    cleanup_failures: List[str],
    first_cause: Optional[BaseException],
    *,
    trigger_fault_injection: Callable[..., None],
    remove_stashed_object_and_verify: Callable[..., bool],
) -> Optional[BaseException]:
    """Execute one existing stashed Object cleanup unit."""
    if not stashed.get("obj_cleaned", False):
        try:
            trigger_fault_injection(
                "during_cleanup_object_removal",
                {"stashed": stashed},
            )
            obj_ref = stashed.get("stashed_obj")
            obj_ptr = stashed.get("stashed_obj_ptr")

            if remove_stashed_object_and_verify(obj_ref, obj_ptr):
                stashed["obj_cleaned"] = True
            else:
                cleanup_failures.append(
                    f"Failed to delete doomed object {stashed.get('original_name')}: still exists in bpy.data.objects"
                )
        except Exception as oe:
            if first_cause is None:
                first_cause = oe
            cleanup_failures.append(
                f"Failed to clean up stashed object {stashed.get('original_name')}: {oe}"
            )

    return first_cause


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _cleanup_stashed_datablock
# PURPOSE: 按 obj_cleaned and not data_cleaned 前置条件调度单个 DataBlock 的故障注入、查找、授权匹配、删除或保留记录
# REASON: 将单个 DataBlock 清理调度迁入 Layer 6，保持四种路径状态标记、first_cause 及 Exception 收集语义不变
def _cleanup_stashed_datablock(
    tx: Any,
    stashed: Dict[str, Any],
    cleanup_failures: List[str],
    first_cause: Optional[BaseException],
    *,
    trigger_fault_injection: Callable[..., None],
    find_stashed_datablock: Callable[..., Any],
    find_datablock_cleanup_authorization: Callable[..., Any],
    remove_authorized_stashed_datablock: Callable[..., None],
    record_preserved_datablock_cleanup: Callable[..., None],
    record_deleted_datablock_cleanup: Callable[..., None],
) -> Optional[BaseException]:
    """Execute one stashed DataBlock cleanup unit."""
    if stashed.get("obj_cleaned", False) and not stashed.get(
        "data_cleaned", False
    ):
        try:
            trigger_fault_injection(
                "during_cleanup_datablock_removal",
                {"stashed": stashed},
            )

            data_ref = stashed.get("stashed_data")
            data_ptr = stashed.get("stashed_data_ptr")
            data_name = stashed.get("stashed_data_name")

            if data_ptr is None and data_ref is None:
                stashed["data_cleaned"] = True
            else:
                target_data, target_coll = find_stashed_datablock(
                    data_ref,
                    data_ptr,
                )

                if target_data is None:
                    stashed["data_cleaned"] = True
                    stashed["data_cleanup_status"] = "DATA_ALREADY_ABSENT"
                else:
                    matching_auth = find_datablock_cleanup_authorization(
                        tx,
                        data_ptr,
                        target_data,
                    )

                    if matching_auth is None:
                        stashed["data_cleanup_status"] = (
                            "PRESERVED_NO_DELETE_AUTHORITY"
                        )
                        stashed["data_cleaned"] = True

                        record_preserved_datablock_cleanup(
                            tx,
                            data_ref,
                            data_ptr,
                            data_name,
                            target_data,
                            target_coll,
                        )
                    else:
                        remove_authorized_stashed_datablock(
                            tx,
                            stashed,
                            matching_auth,
                            data_ptr,
                            data_name,
                            target_data,
                            target_coll,
                            trigger_fault_injection=trigger_fault_injection,
                        )

                        stashed["data_cleaned"] = True
                        stashed["data_cleanup_status"] = "PHYSICALLY_DELETED"

                        record_deleted_datablock_cleanup(
                            tx,
                            data_ref,
                            data_ptr,
                            data_name,
                            target_data,
                            target_coll,
                        )

        except Exception as de:
            if first_cause is None:
                first_cause = de

            cleanup_failures.append(
                f"Failed to clean up datablock for {stashed.get('original_name')}: {de}"
            )

    return first_cause


# [INTRODUCED 2026-11-24T19:31:00+08:00]
# NODE: 10-B / L6-02
# FUNCTION: _execute_stashed_cleanup_pass
# PURPOSE: 执行完整提交后清理流水线：状态禁用拒绝、Constraint 清理、Object 清理与 DataBlock 清理顺序调度、双完成条目移出及结果构造
# REASON: 将 retry_cleanup() 整体执行器迁入 Layer 6，保持幂等队列与单套清理机制同时保留 arm_ik.py 纯兼容代理
def _execute_stashed_cleanup_pass(
    tx: Any,
    *,
    transaction_state_cls: Any,
    authorized_remove_constraint: Callable[..., Any],
    cleanup_stashed_constraints: Callable[..., Any],
    cleanup_stashed_object: Callable[..., Any],
    trigger_fault_injection: Callable[..., None],
    remove_stashed_object_and_verify: Callable[..., bool],
    find_stashed_datablock: Callable[..., Any],
    find_datablock_cleanup_authorization: Callable[..., Any],
    remove_authorized_stashed_datablock: Callable[..., None],
    record_preserved_datablock_cleanup: Callable[..., None],
    record_deleted_datablock_cleanup: Callable[..., None],
    build_cleanup_result: Callable[..., Any],
    cleanup_outcome_cls: Any,
    cleanup_result_cls: Any,
) -> Any:
    """Execute the existing post-commit stashed resource cleanup pass."""
    if tx.state in (
        transaction_state_cls.FAILED,
        transaction_state_cls.ROLLING_BACK,
        transaction_state_cls.ROLLED_BACK,
        transaction_state_cls.ACTIVE,
        transaction_state_cls.SNAPSHOTTING,
        transaction_state_cls.CREATED,
    ):
        raise RuntimeError(
            f"Cannot execute retry_cleanup on transaction {tx.tx_id} in state {tx.state}: "
            f"FAILED -> COMMITTED transition is strictly forbidden"
        )

    cleanup_failures: List[str] = []
    first_cause: Optional[BaseException] = None

    first_cause = cleanup_stashed_constraints(
        tx,
        cleanup_failures,
        first_cause,
        authorized_remove_constraint=authorized_remove_constraint,
    )

    for stashed in list(tx.uncleaned_stashed_objects):
        first_cause = cleanup_stashed_object(
            stashed,
            cleanup_failures,
            first_cause,
            trigger_fault_injection=trigger_fault_injection,
            remove_stashed_object_and_verify=(
                remove_stashed_object_and_verify
            ),
        )

        first_cause = _cleanup_stashed_datablock(
            tx,
            stashed,
            cleanup_failures,
            first_cause,
            trigger_fault_injection=trigger_fault_injection,
            find_stashed_datablock=find_stashed_datablock,
            find_datablock_cleanup_authorization=(
                find_datablock_cleanup_authorization
            ),
            remove_authorized_stashed_datablock=(
                remove_authorized_stashed_datablock
            ),
            record_preserved_datablock_cleanup=(
                record_preserved_datablock_cleanup
            ),
            record_deleted_datablock_cleanup=(
                record_deleted_datablock_cleanup
            ),
        )

        if stashed.get("obj_cleaned", False) and stashed.get(
            "data_cleaned", False
        ):
            if stashed in tx.uncleaned_stashed_objects:
                tx.uncleaned_stashed_objects.remove(stashed)

    return build_cleanup_result(
        tx,
        cleanup_failures,
        first_cause,
        cleanup_outcome_cls=cleanup_outcome_cls,
        cleanup_result_cls=cleanup_result_cls,
    )
