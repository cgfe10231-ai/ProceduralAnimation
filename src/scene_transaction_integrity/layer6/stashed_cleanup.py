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
