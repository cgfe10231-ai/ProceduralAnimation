"""Public cross-layer dependency wiring boundary for the 6-layer Scene Transaction Integrity system (Task 10-B).

Passes data, function references, and cross-layer dependencies between existing
single-owner layer implementations without holding registries, transaction
lifecycle state, authorization decisions, or resource CRUD logic.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

import bpy
from mathutils import Matrix

from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    DEFAULT_POLE_BACKWARD_OFFSET,
    DEFAULT_POLE_OUTWARD_OFFSET,
    ELBOW_REST_Z,
    HAND_ROT_CONSTRAINT_NAMES,
    MAX_ARM_REACH,
    MIN_ARM_REACH,
    SHOULDER_X_OFFSET,
    WRIST_REST_Z,
)
from src.rig.transform_utils import (
    apply_target_rotation,
    compute_effective_parent_matrix,
    validate_effective_parent_transform,
    world_to_local_position,
    world_to_local_rotation_quaternion,
)
from src.scene_transaction_integrity import fault_injection as _fault_injection
from src.scene_transaction_integrity.layer1 import (
    authorization_grants as _layer1_auth_grants,
    authorization_registry as _layer1_auth_registry,
    cleanup_validation as _layer1_cleanup_validation,
    isolation_governance as _layer1_isolation_governance,
    outermost_admission as _layer1_outermost_admission,
    pending_cleanup as _layer1_pending_cleanup,
    post_commit_cleanup as _layer1_post_commit_cleanup,
    session_liveness as _layer1_session_liveness,
    transaction_coordinator as _layer1_tx_coordinator,
)
from src.scene_transaction_integrity.layer2 import (
    audit_registries as _layer2_audit_registries,
    identity_helpers as _layer2_identity_helpers,
    isolation_transition as _layer2_isolation_transition,
    session_registries as _layer2_session_registries,
    session_verification as _layer2_session_verification,
)
from src.scene_transaction_integrity.layer2.relationship_states import (
    _RelationshipOperationState,
)
from src.scene_transaction_integrity.layer2.session_records import (
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _ISOLATED_FAILED_ARMATURES,
    _MANAGED_ARMATURE_IDENTITIES,
)
from src.scene_transaction_integrity.layer2.tombstone_registry import (
    _ARCHIVED_FAILED_D_TOMBSTONES,
)
from src.scene_transaction_integrity.layer2.pending_cleanup_registry import (
    _PENDING_ARM_RIG_CLEANUPS,
)
from src.scene_transaction_integrity.layer2.transaction_context import (
    _ArmRigTransactionContext,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
    _FailedTransactionClass,
)
from src.scene_transaction_integrity.layer3 import (
    character_collection_creation as _layer3_char_col_creation,
    collection_child_link as _layer3_col_child_link,
    collection_child_unlink as _layer3_col_child_unlink,
    collection_object_link as _layer3_col_obj_link,
    collection_object_unlink as _layer3_col_obj_unlink,
    collection_queries as _layer3_col_queries,
    constraint_creation as _layer3_con_creation,
    constraint_removal as _layer3_con_removal,
    constraint_target_assignment as _layer3_con_target_assign,
    constraint_target_pair_classifier as _layer3_con_pair_classifier,
    constraint_target_unit as _layer3_con_target_unit,
    controller_creation as _layer3_ctrl_creation,
    controller_ownership as _layer3_ctrl_ownership,
    controller_recovery_authority as _layer3_ctrl_recovery_auth,
    datablock_removal as _layer3_datablock_removal,
    object_parent_assignment as _layer3_obj_parent_assign,
    relationship_reversal as _layer3_rel_reversal,
    resource_contracts as _layer3_resource_contracts,
    snapshot_relationship_restoration as _layer3_snap_rel_restore,
    stashed_object_removal as _layer3_stashed_obj_removal,
)
from src.scene_transaction_integrity.layer4 import (
    depsgraph as _layer4_depsgraph,
    hand_target as _layer4_hand_target,
    influence as _layer4_influence,
    preflight as _layer4_preflight,
    reset as _layer4_reset,
    setup as _layer4_setup,
    state_query as _layer4_state_query,
)
from src.scene_transaction_integrity.layer5 import (
    isolation_evidence as _layer5_isolation_evidence,
    rollback_execution as _layer5_rollback_execution,
    rollback_verification as _layer5_rollback_verification,
    snapshot_capture as _layer5_snapshot_capture,
)
from src.scene_transaction_integrity.layer6 import (
    cleanup_results as _layer6_cleanup_results,
    stashed_cleanup as _layer6_stashed_cleanup,
)


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _update_arm_ik_depsgraph
# PURPOSE: 装配共享故障注入触发器与 Layer 4 依赖图更新器
# REASON: 将原位于 arm_ik.py 的跨模块依赖装配迁入六层公共接线边界
def _update_arm_ik_depsgraph() -> None:
    """Synchronize the dependency graph for Arm IK calculations within mutations."""
    return _layer4_depsgraph._update_arm_ik_depsgraph(
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _ensure_character_collection
# PURPOSE: 装配 Layer 2 活动栈/状态枚举、共享故障注入及 Layer 3 子集合链接与补偿回调以获取或创建 Character 集合
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _ensure_character_collection() -> bpy.types.Collection:
    """Ensure the Character collection exists in the active scene with strict registration-before-link order (F14-06)."""
    return _layer3_char_col_creation._ensure_character_collection(
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        cleanup_failed_character_collection_registration=(
            _layer3_char_col_creation._cleanup_failed_character_collection_registration
        ),
        authorized_link_child_collection=_authorized_link_child_collection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_link_object_to_collection
# PURPOSE: 装配 Layer 2 事务栈与关系枚举、Layer 3 身份查询及共享故障注入以执行受权对象入集链接
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_link_object_to_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object link executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_col_obj_link._authorized_link_object_to_collection(
        collection,
        obj,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        is_object_linked_to_collection_by_identity=(
            _layer3_col_queries._is_object_linked_to_collection_by_identity
        ),
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_unlink_object_from_collection
# PURPOSE: 装配 Layer 2 事务栈与关系枚举、Layer 3 身份查询及共享故障注入以执行受权对象退集解绑
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_unlink_object_from_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
    category: str = "TX_UNLINKED_ORIGINAL",
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object unlink executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_col_obj_unlink._authorized_unlink_object_from_collection(
        collection,
        obj,
        active_tx=active_tx,
        category=category,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        relationship_operation_state_cls=_RelationshipOperationState,
        is_object_linked_to_collection_by_identity=(
            _layer3_col_queries._is_object_linked_to_collection_by_identity
        ),
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_assign_object_parent
# PURPOSE: 装配 Layer 2 状态与关系枚举、Layer 3 控制器权限核验、共形父级校验及共享故障注入以执行受权父级赋值
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_assign_object_parent(
    obj: bpy.types.Object,
    parent: Optional[bpy.types.Object],
    matrix_parent_inverse: Optional[Matrix] = None,
    active_tx: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Object Parent and Matrix Parent Inverse assignment under 7-state protocol."""
    return _layer3_obj_parent_assign._authorized_assign_object_parent(
        obj,
        parent,
        matrix_parent_inverse=matrix_parent_inverse,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        verify_controller_object_transaction_authority=(
            _layer3_ctrl_ownership._verify_controller_object_transaction_authority
        ),
        matrix_equals=_layer3_resource_contracts._matrix_equals,
        validate_effective_parent_transform=validate_effective_parent_transform,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        matrix_cls=Matrix,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_link_child_collection
# PURPOSE: 装配 Layer 2 状态与关系枚举、Layer 3 子集合归属核验及共享故障注入以执行受权子集合链接
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_link_child_collection(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Optional[Any] = None,
    category: str = "TX_ADDED",
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection child linking executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_col_child_link._authorized_link_child_collection(
        parent_collection,
        child_collection,
        active_tx=active_tx,
        category=category,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        is_collection_descendant_of=_layer3_col_queries._is_collection_descendant_of,
        is_child_collection_linked_by_identity=(
            _layer3_col_queries._is_child_collection_linked_by_identity
        ),
        require_collection_child_relationship_ownership=(
            _layer3_col_child_link._require_collection_child_relationship_ownership
        ),
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        relationship_operation_state_cls=_RelationshipOperationState,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_unlink_child_collection
# PURPOSE: 装配 Layer 2 状态与关系枚举、Layer 3 子集合归属核验及共享故障注入以执行受权子集合解绑
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_unlink_child_collection(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Optional[Any] = None,
    category: str = "TX_UNLINKED_ORIGINAL",
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection child unlinking executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    return _layer3_col_child_unlink._authorized_unlink_child_collection(
        parent_collection,
        child_collection,
        active_tx=active_tx,
        category=category,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        relationship_operation_state_cls=_RelationshipOperationState,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        is_child_collection_linked_by_identity=(
            _layer3_col_queries._is_child_collection_linked_by_identity
        ),
        require_collection_child_relationship_ownership=(
            _layer3_col_child_link._require_collection_child_relationship_ownership
        ),
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_create_constraint
# PURPOSE: 装配 Layer 1 会话身份调度、Layer 2 事务栈/状态、Layer 3 局部补偿及共享故障注入以受权创建约束
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_create_constraint(
    pbone: bpy.types.PoseBone,
    con_type: str,
    con_name: str,
    active_tx: Optional[Any] = None,
    arm: Optional[bpy.types.Object] = None,
) -> bpy.types.Constraint:
    """Layer 3 authorized creation of a managed constraint on a pose bone."""
    return _layer3_con_creation._authorized_create_constraint(
        pbone,
        con_type,
        con_name,
        active_tx=active_tx,
        arm=arm,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        ensure_armature_session_identity=_layer1_session_liveness.ensure_armature_session_identity,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        cleanup_failed_constraint_creation=_layer3_con_creation._cleanup_failed_constraint_creation,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_remove_constraint
# PURPOSE: 装配 Layer 2 事务栈与状态枚举及共享故障注入以受权移除约束
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_remove_constraint(
    pbone: bpy.types.PoseBone,
    con_record_or_ref: Any,
    phase: str,
    active_tx: Optional[Any] = None,
) -> bool:
    """Layer 3 authoritative removal of a managed constraint."""
    return _layer3_con_removal._authorized_remove_constraint(
        pbone,
        con_record_or_ref,
        phase,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_state_cls=_ArmRigTransactionState,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _apply_single_constraint_target_unit
# PURPOSE: 装配 Layer 2 关系状态枚举、Layer 3 对象身份核验及共享故障注入以执行单个约束目标赋值单元
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _apply_single_constraint_target_unit(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    field: str,
    subtarget_field: str,
    target_obj: Optional[bpy.types.Object],
    target_subtarget: str,
    intended_mutation: str,
    active_tx: Optional[Any],
) -> Optional[Dict[str, Any]]:
    """Execute a single constraint target or pole target assignment unit under 7-state protocol."""
    return _layer3_con_target_unit._apply_single_constraint_target_unit(
        pbone,
        con,
        field,
        subtarget_field,
        target_obj,
        target_subtarget,
        intended_mutation,
        active_tx,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_assign_constraint_targets
# PURPOSE: 装配 Layer 2 事务栈与关系状态枚举、Layer 3 对象身份核验及共享故障注入以受权赋值约束目标
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_assign_constraint_targets(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    target: Any = _layer3_resource_contracts._TARGET_UNSET,
    subtarget: Any = _layer3_resource_contracts._TARGET_UNSET,
    pole_target: Any = _layer3_resource_contracts._TARGET_UNSET,
    pole_subtarget: Any = _layer3_resource_contracts._TARGET_UNSET,
    active_tx: Optional[Any] = None,
) -> None:
    """Layer 3 authorized constraint target and pole target assignment."""
    return _layer3_con_target_assign._authorized_assign_constraint_targets(
        pbone,
        con,
        target=target,
        subtarget=subtarget,
        pole_target=pole_target,
        pole_subtarget=pole_subtarget,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_revert_relationship_record
# PURPOSE: 装配 Layer 2 关系状态枚举、Layer 3 身份核验与目标分类器及共享故障注入以逆向撤销单条关系日志记录
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_revert_relationship_record(
    op_record: Dict[str, Any],
    active_tx: Any,
    restoration_errors: List[str],
) -> None:
    """Layer 3 atomic reversal of a single relationship operation record."""
    return _layer3_rel_reversal._authorized_revert_relationship_record(
        op_record,
        active_tx,
        restoration_errors,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        classify_constraint_target_pair_effect=(
            _layer3_con_pair_classifier._classify_constraint_target_pair_effect
        ),
        matrix_equals=_layer3_resource_contracts._matrix_equals,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        is_child_collection_linked_by_identity=(
            _layer3_col_queries._is_child_collection_linked_by_identity
        ),
        is_object_linked_to_collection_by_identity=(
            _layer3_col_queries._is_object_linked_to_collection_by_identity
        ),
        bpy_module=bpy,
        matrix_cls=Matrix,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_restore_relationship
# PURPOSE: 装配受权关系逆向撤销回调以恢复指定类型的关系记录
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_restore_relationship(
    active_tx: Optional[Any],
    snapshot: Optional[Dict[str, Any]],
    restoration_errors: List[str],
    mutation_type: Optional[str] = None,
) -> None:
    """Authoritatively revert and restore relationships via Layer 3 records."""
    return _layer3_rel_reversal._authorized_restore_relationship(
        active_tx,
        snapshot,
        restoration_errors,
        mutation_type=mutation_type,
        authorized_revert_relationship_record=_authorized_revert_relationship_record,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _authorized_restore_collection_object_relationships
# PURPOSE: 装配受权关系逆向撤销与 Layer 3 身份/权限核验回调以恢复集合与对象成员关系
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _authorized_restore_collection_object_relationships(
    active_tx: Optional[Any],
    snapshot: Dict[str, Any],
    restoration_errors: List[str],
    phase: str = "ALL",
) -> None:
    """Layer 3 authoritative rollback and restoration of Collection <-> Object relationships."""
    return _layer3_snap_rel_restore._authorized_restore_collection_object_relationships(
        active_tx,
        snapshot,
        restoration_errors,
        phase=phase,
        authorized_revert_relationship_record=_authorized_revert_relationship_record,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        is_object_linked_to_collection_by_identity=(
            _layer3_col_queries._is_object_linked_to_collection_by_identity
        ),
        verify_controller_object_transaction_authority=(
            _layer3_ctrl_ownership._verify_controller_object_transaction_authority
        ),
        authorized_ensure_snapshot_collection_link=(
            _layer3_snap_rel_restore._authorized_ensure_snapshot_collection_link
        ),
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _get_or_create_empty
# PURPOSE: 装配 Layer 2 活动栈、Layer 3 所有权核验与受权关系操作及共享故障注入以获取或创建 Empty 控制器
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _get_or_create_empty(
    name: str,
    display_type: str,
    display_size: float,
    parent: Optional[bpy.types.Object],
    collection: bpy.types.Collection,
) -> Tuple[bpy.types.Object, bool]:
    """Retrieve or construct an Empty control object preserving existing parent and transform."""
    return _layer3_ctrl_creation._get_or_create_empty(
        name,
        display_type,
        display_size,
        parent,
        collection,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        verify_transaction_wrong_type_object_ownership=(
            _layer3_ctrl_ownership._verify_transaction_wrong_type_object_ownership
        ),
        authorized_unlink_object_from_collection=_authorized_unlink_object_from_collection,
        authorized_link_object_to_collection=_authorized_link_object_to_collection,
        authorized_assign_object_parent=_authorized_assign_object_parent,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        matrix_cls=Matrix,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _snapshot_arm_rig_state
# PURPOSE: 装配领域配置、Layer 2 事务栈、Layer 3 对象身份核验、Layer 4 依赖图更新及共享故障注入以捕获快照
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界，并保持与 Layer 5 单一快照实现动态绑定
def _snapshot_arm_rig_state(arm: bpy.types.Object) -> Dict[str, Any]:
    """Capture full production state snapshot of Arm IK controllers, pose bones, constraints, and collections."""
    return _layer5_snapshot_capture._snapshot_arm_rig_state(
        arm,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _rollback_arm_rig_state
# PURPOSE: 装配 Layer 2 注册表/状态、Layer 3 受权关系与删除恢复、Layer 4 依赖图更新及共享故障注入以执行回滚
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _rollback_arm_rig_state(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Restore the Arm IK rig state precisely to the recorded snapshot."""
    return _layer5_rollback_execution._rollback_arm_rig_state(
        arm=arm,
        snapshot=snapshot,
        active_tx=active_tx,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        transaction_state_cls=_ArmRigTransactionState,
        relationship_operation_state_cls=_RelationshipOperationState,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        authorized_revert_relationship_record=_authorized_revert_relationship_record,
        authorized_restore_collection_object_relationships=(
            _authorized_restore_collection_object_relationships
        ),
        controller_role_for_name=_layer3_ctrl_ownership._controller_role_for_name,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        verify_controller_object_transaction_authority=(
            _layer3_ctrl_ownership._verify_controller_object_transaction_authority
        ),
        controller_is_borrowed_by_other_armature=(
            _layer3_ctrl_ownership._controller_is_borrowed_by_other_armature
        ),
        verify_failed_isolation_controller_recovery_authority=(
            _layer3_ctrl_recovery_auth._verify_failed_isolation_controller_recovery_authority
        ),
        authorized_restore_snapshot_object_parent=(
            _layer3_snap_rel_restore._authorized_restore_snapshot_object_parent
        ),
        matrix_equals=_layer3_resource_contracts._matrix_equals,
        authorized_remove_constraint=_authorized_remove_constraint,
        authorized_restore_snapshot_constraint_targets_without_tx=(
            _layer3_snap_rel_restore._authorized_restore_snapshot_constraint_targets_without_tx
        ),
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        is_child_collection_linked_by_identity=(
            _layer3_col_queries._is_child_collection_linked_by_identity
        ),
        authorized_restore_snapshot_collection_child=(
            _layer3_snap_rel_restore._authorized_restore_snapshot_collection_child
        ),
        authorized_ensure_snapshot_collection_link=(
            _layer3_snap_rel_restore._authorized_ensure_snapshot_collection_link
        ),
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _verify_arm_rig_state_restored
# PURPOSE: 装配跨层快照入口与 Layer 2 事务栈及关系状态枚举以验证回滚后状态完全一致
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _verify_arm_rig_state_restored(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Verify that current Arm IK rig state precisely matches the snapshot."""
    return _layer5_rollback_verification._verify_arm_rig_state_restored(
        arm=arm,
        snapshot=snapshot,
        active_tx=active_tx,
        snapshot_arm_rig_state=_snapshot_arm_rig_state,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        relationship_operation_state_cls=_RelationshipOperationState,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: verify_armature_deisolation_evidence
# PURPOSE: 装配 Layer 1 存活扫描、Layer 2 单一身份核验与注册表、Layer 3 实体查询及 Layer 5 状态恢复核验
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界，动态解析统一身份核验实现以消除分裂绑定
def verify_armature_deisolation_evidence(
    arm: Optional[bpy.types.Object] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Layer 5: Read-only verification of recovery evidence before de-isolating an Armature (Section 8.2)."""
    return _layer5_isolation_evidence.verify_armature_deisolation_evidence(
        arm=arm,
        session_id=session_id,
        sweep_dead_managed_armature_identities=(
            _layer1_session_liveness._sweep_dead_managed_armature_identities
        ),
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        archived_failed_d_tombstones=_ARCHIVED_FAILED_D_TOMBSTONES,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        armature_liveness_status_cls=_ArmatureLivenessStatus,
        armature_isolation_state_cls=_ArmatureIsolationState,
        failed_transaction_class_cls=_FailedTransactionClass,
        relationship_operation_state_cls=_RelationshipOperationState,
        verify_armature_session_identity_record=(
            _layer2_session_verification._verify_armature_session_identity_record
        ),
        verify_arm_rig_state_restored=_verify_arm_rig_state_restored,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _verify_dead_armature_tombstone_retirement_evidence
# PURPOSE: 装配 Layer 1 存活扫描、Layer 2 单一存活核验与注册表及 Layer 3 实体身份查询以核验墓碑退休条件
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界，动态解析统一存活核验实现以消除分裂绑定
def _verify_dead_armature_tombstone_retirement_evidence(
    session_id: str,
) -> Dict[str, Any]:
    """Layer 5: Read-only verification of dead Armature tombstone retirement conditions (Section 8.2 Case 3)."""
    return _layer5_isolation_evidence._verify_dead_armature_tombstone_retirement_evidence(
        session_id=session_id,
        sweep_dead_managed_armature_identities=(
            _layer1_session_liveness._sweep_dead_managed_armature_identities
        ),
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        failed_transaction_class_cls=_FailedTransactionClass,
        armature_isolation_state_cls=_ArmatureIsolationState,
        check_original_object_liveness=_layer2_identity_helpers._check_original_object_liveness,
        find_live_object_by_identity=_layer3_resource_contracts._find_live_object_by_identity,
        find_live_collection_by_identity=_layer3_char_col_creation._find_live_collection_by_identity,
        pending_arm_rig_cleanups=_PENDING_ARM_RIG_CLEANUPS,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _issue_coordinator_authorization_grant
# PURPOSE: 装配 Layer 1 Grant 注册表与回收器、Layer 2 隔离与会话注册表及 Layer 5 恢复/墓碑证据核验入口
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界
def _issue_coordinator_authorization_grant(
    session_id: str,
    transition_action: str = "CLEAR_TO_NONE",
    arm: Optional[bpy.types.Object] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Issue a single-use internal authorization grant binding verified Layer 5 recovery evidence."""
    return _layer1_auth_grants._issue_coordinator_authorization_grant(
        session_id,
        transition_action=transition_action,
        arm=arm,
        coordinator_authorization_grants=_layer1_auth_registry._COORDINATOR_AUTHORIZATION_GRANTS,
        coordinator_grant_ttl_seconds=_layer1_auth_registry._COORDINATOR_GRANT_TTL_SECONDS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        coordinator_reap_stale_authorization_grants=(
            _layer1_auth_grants._coordinator_reap_stale_authorization_grants
        ),
        coordinator_revoke_session_authorization_grants=(
            _layer1_auth_grants._coordinator_revoke_session_authorization_grants
        ),
        verify_deisolation_evidence=verify_armature_deisolation_evidence,
        verify_dead_armature_tombstone_retirement_evidence=(
            _verify_dead_armature_tombstone_retirement_evidence
        ),
        failed_transaction_class_cls=_FailedTransactionClass,
        armature_isolation_state_cls=_ArmatureIsolationState,
        legacy_kwargs=kwargs,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _clear_or_retire_failure_isolation_by_coordinator
# PURPOSE: 装配 Layer 1 Grant 凭据生命周期、Layer 2 隔离与墓碑注册表及 Layer 5 实时证据核验回调
# REASON: 将原位于 arm_ik.py 的跨层依赖装配迁入六层公共接线边界，保持 Layer 2 不反向导入 Layer 1 与 Layer 5
def _clear_or_retire_failure_isolation_by_coordinator(
    session_id: str,
    action: str,
    reason: str,
    authorization_grant: Optional[Dict[str, Any]] = None,
    verification_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer 2: Clear FAILED-B/C isolation or archive FAILED-D tombstone exclusively for Layer 1 Coordinator."""
    return _layer2_isolation_transition._clear_or_retire_failure_isolation_by_coordinator(
        session_id,
        action,
        reason,
        authorization_grant=authorization_grant,
        verification_evidence=verification_evidence,
        archived_failed_d_tombstones=_ARCHIVED_FAILED_D_TOMBSTONES,
        coordinator_authorization_grants=_layer1_auth_registry._COORDINATOR_AUTHORIZATION_GRANTS,
        coordinator_grant_ttl_seconds=_layer1_auth_registry._COORDINATOR_GRANT_TTL_SECONDS,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        coordinator_reap_stale_authorization_grants=(
            _layer1_auth_grants._coordinator_reap_stale_authorization_grants
        ),
        coordinator_revoke_session_authorization_grants=(
            _layer1_auth_grants._coordinator_revoke_session_authorization_grants
        ),
        verify_deisolation_evidence=verify_armature_deisolation_evidence,
        verify_dead_armature_tombstone_retirement_evidence=(
            _verify_dead_armature_tombstone_retirement_evidence
        ),
        armature_isolation_state_cls=_ArmatureIsolationState,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: request_armature_deisolation
# PURPOSE: 装配 Layer 1 Grant 签发、Layer 2 隔离清理与审计记录及 Layer 5 恢复证据核验入口
# REASON: 将原位于 arm_ik.py 的解除隔离协调器依赖装配迁入六层公共接线边界
def request_armature_deisolation(
    arm: Optional[bpy.types.Object],
    reason: str,
    session_id: Optional[str] = None,
    raise_on_reject: bool = False,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Evaluate Layer 5 evidence and authorize or reject de-isolation (Section 8.1/8.3)."""
    return _layer1_isolation_governance.request_armature_deisolation(
        arm=arm,
        reason=reason,
        session_id=session_id,
        raise_on_reject=raise_on_reject,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        verify_deisolation_evidence=verify_armature_deisolation_evidence,
        issue_coordinator_authorization_grant=_issue_coordinator_authorization_grant,
        clear_or_retire_failure_isolation_by_coordinator=(
            _clear_or_retire_failure_isolation_by_coordinator
        ),
        append_deisolation_audit=_layer2_audit_registries._append_deisolation_audit,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: retire_dead_armature_tombstone
# PURPOSE: 装配 Layer 1 Grant 签发、Layer 2 墓碑归档与审计记录及 Layer 5 墓碑退休证据核验入口
# REASON: 将原位于 arm_ik.py 的死亡骨架墓碑退休协调器依赖装配迁入六层公共接线边界
def retire_dead_armature_tombstone(
    session_id: str,
    reason: str,
    raise_on_reject: bool = False,
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Verify dead Armature tombstone retirement evidence and transition to ARCHIVED_RETIRED."""
    return _layer1_isolation_governance.retire_dead_armature_tombstone(
        session_id=session_id,
        reason=reason,
        raise_on_reject=raise_on_reject,
        verify_dead_armature_tombstone_retirement_evidence=(
            _verify_dead_armature_tombstone_retirement_evidence
        ),
        issue_coordinator_authorization_grant=_issue_coordinator_authorization_grant,
        clear_or_retire_failure_isolation_by_coordinator=(
            _clear_or_retire_failure_isolation_by_coordinator
        ),
        append_deisolation_audit=_layer2_audit_registries._append_deisolation_audit,
    )


# [INTRODUCED 2026-11-25T21:28:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION-fix-1
# FUNCTION: _create_arm_rig_transaction_context
# PURPOSE: 在公共接线边界显式装配 15 项跨层依赖并构造 Layer 2 唯一 _ArmRigTransactionContext 实例，保持构造入口与真实类对象分离
# REASON: 移除 Layer 2 事务上下文隐式回调表与绕过 Layer 1 的备用路径，统一覆盖正常外层事务与 FAILED 准入证据事务构造接线
def _create_arm_rig_transaction_context(
    arm: bpy.types.Object,
    session_record: Optional[Any] = None,
) -> _ArmRigTransactionContext:
    """Construct a Layer 2 _ArmRigTransactionContext with all 15 cross-layer dependencies wired explicitly."""
    return _ArmRigTransactionContext(
        arm,
        session_record=session_record,
        ensure_armature_session_identity=(
            _layer1_session_liveness.ensure_armature_session_identity
        ),
        find_live_object_by_identity=(
            _layer3_resource_contracts._find_live_object_by_identity
        ),
        controller_role_for_name=_layer3_ctrl_ownership._controller_role_for_name,
        find_live_collection_by_identity=(
            _layer3_char_col_creation._find_live_collection_by_identity
        ),
        execute_stashed_cleanup_pass=(
            _layer6_stashed_cleanup._execute_stashed_cleanup_pass
        ),
        authorized_remove_constraint=_authorized_remove_constraint,
        cleanup_stashed_constraints=(
            _layer6_stashed_cleanup._cleanup_stashed_constraints
        ),
        cleanup_stashed_object=_layer6_stashed_cleanup._cleanup_stashed_object,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        remove_stashed_object_and_verify=(
            _layer3_stashed_obj_removal._remove_stashed_object_and_verify
        ),
        find_stashed_datablock=_layer3_datablock_removal._find_stashed_datablock,
        remove_authorized_stashed_datablock=(
            _layer3_datablock_removal._remove_authorized_stashed_datablock
        ),
        build_cleanup_result=_layer6_cleanup_results._build_cleanup_result,
        cleanup_outcome_cls=_layer6_cleanup_results._CleanupOutcome,
        cleanup_result_cls=_layer6_cleanup_results._CleanupResult,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _arm_rig_transaction
# PURPOSE: 装配 Layer 1 门禁/清理裁决、Layer 2 唯一事务上下文与身份核验、Layer 4 依赖图更新、Layer 5 快照回滚及共享故障注入
# REASON: 将原位于 arm_ik.py 的事务协调上下文管理器跨层接线迁入六层公共接线边界，供领域层与 WBC 统一调用
@contextmanager
def _arm_rig_transaction(arm: bpy.types.Object) -> Generator[_ArmRigTransactionContext, None, None]:
    """Context manager executing Arm IK mutations under atomic transaction protection."""
    yield from _layer1_tx_coordinator._arm_rig_transaction(
        arm,
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        transaction_context_cls=_ArmRigTransactionContext,
        transaction_context_factory=_create_arm_rig_transaction_context,
        transaction_state_cls=_ArmRigTransactionState,
        failed_transaction_class_cls=_FailedTransactionClass,
        relationship_operation_state_cls=_RelationshipOperationState,
        ensure_armature_session_identity=_layer1_session_liveness.ensure_armature_session_identity,
        assert_arm_rig_cleanup_gate=_layer1_outermost_admission._assert_arm_rig_cleanup_gate,
        assert_arm_rig_failed_isolation_gate=(
            _layer1_outermost_admission._assert_arm_rig_failed_isolation_gate
        ),
        verify_armature_session_identity_record=(
            _layer2_session_verification._verify_armature_session_identity_record
        ),
        record_armature_failure_isolation_by_coordinator=(
            _layer2_session_registries._record_armature_failure_isolation_by_coordinator
        ),
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        capture_pre_snapshot_structural_fingerprint=(
            _layer5_snapshot_capture._capture_pre_snapshot_structural_fingerprint
        ),
        snapshot_arm_rig_state=_snapshot_arm_rig_state,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        rollback_arm_rig_state=_rollback_arm_rig_state,
        verify_arm_rig_state_restored=_verify_arm_rig_state_restored,
        verify_pre_write_zero_mutation_and_integrity=(
            _layer5_snapshot_capture._verify_pre_write_zero_mutation_and_integrity
        ),
        coordinator_validate_cleanup_preflight=(
            _layer1_cleanup_validation._coordinator_validate_cleanup_preflight
        ),
        coordinator_preserve_cleanup_pending=(
            _layer1_pending_cleanup._coordinator_preserve_cleanup_pending
        ),
        coordinator_apply_cleanup_result=(
            _layer1_post_commit_cleanup._coordinator_apply_cleanup_result
        ),
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: _preflight_arm_ik_parent_transforms
# PURPOSE: 装配 Layer 2 活动栈、Layer 3 控制器归属核验、有效父级矩阵数学域及领域配置以执行零写入预检
# REASON: 将原位于 arm_ik.py 的预检跨层依赖装配迁入六层公共接线边界
def _preflight_arm_ik_parent_transforms(
    arm: bpy.types.Object,
    valid_side: str,
    root_obj: Optional[bpy.types.Object],
) -> Tuple[bool, Matrix, Matrix]:
    """Preflight check effective parent transform domains before any scene mutation (Task 10-B-2 & 10-B-3)."""
    return _layer4_preflight._preflight_arm_ik_parent_transforms(
        arm,
        valid_side,
        root_obj,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        verify_transaction_wrong_type_object_ownership=(
            _layer3_ctrl_ownership._verify_transaction_wrong_type_object_ownership
        ),
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        compute_effective_parent_matrix=compute_effective_parent_matrix,
        validate_effective_parent_transform=validate_effective_parent_transform,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: setup_arm_ik
# PURPOSE: 为 Layer 4 唯一 setup_arm_ik 实现装配六层事务门禁、受权资源接口、故障注入及上肢领域配置
# REASON: 彻底移出 arm_ik.py 中的六层内部依赖装配，使 arm_ik.py 不持有任何事务注册表或受权内部符号
def setup_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    initial_influence: float = 0.0,
) -> Dict[str, bpy.types.Object]:
    """Wired Layer 4 setup_arm_ik entrypoint."""
    return _layer4_setup.setup_arm_ik(
        armature_obj,
        initial_influence,
        arm_rig_transaction=_arm_rig_transaction,
        assert_arm_rig_cleanup_gate=_layer1_outermost_admission._assert_arm_rig_cleanup_gate,
        assert_arm_rig_failed_isolation_gate=(
            _layer1_outermost_admission._assert_arm_rig_failed_isolation_gate
        ),
        active_transaction_stack=_ACTIVE_TRANSACTION_STACK,
        managed_armature_identities=_MANAGED_ARMATURE_IDENTITIES,
        isolated_failed_armatures=_ISOLATED_FAILED_ARMATURES,
        armature_isolation_state=_ArmatureIsolationState,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        verify_transaction_wrong_type_object_ownership=(
            _layer3_ctrl_ownership._verify_transaction_wrong_type_object_ownership
        ),
        ensure_character_collection=_ensure_character_collection,
        get_or_create_empty=_get_or_create_empty,
        authorized_create_constraint=_authorized_create_constraint,
        authorized_assign_constraint_targets=_authorized_assign_constraint_targets,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        uuid4=uuid.uuid4,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        shoulder_x_offset=SHOULDER_X_OFFSET,
        wrist_rest_z=WRIST_REST_Z,
        elbow_rest_z=ELBOW_REST_Z,
        default_pole_outward_offset=DEFAULT_POLE_OUTWARD_OFFSET,
        default_pole_backward_offset=DEFAULT_POLE_BACKWARD_OFFSET,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: set_arm_ik_influence
# PURPOSE: 为 Layer 4 唯一 set_arm_ik_influence 实现装配事务协调器、控制器归属核验、故障注入与领域配置
# REASON: 彻底移出 arm_ik.py 中的六层内部依赖装配
def set_arm_ik_influence(
    armature_obj: Optional[bpy.types.Object] = None,
    side: str = "BOTH",
    influence: float = 1.0,
) -> None:
    """Wired Layer 4 set_arm_ik_influence entrypoint."""
    return _layer4_influence.set_arm_ik_influence(
        armature_obj,
        side,
        influence,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        arm_rig_transaction=_arm_rig_transaction,
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: reset_arm_ik
# PURPOSE: 为 Layer 4 唯一 reset_arm_ik 实现装配事务协调器、控制器归属核验、有效父级变换与领域配置
# REASON: 彻底移出 arm_ik.py 中的六层内部依赖装配
def reset_arm_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Wired Layer 4 reset_arm_ik entrypoint."""
    return _layer4_reset.reset_arm_ik(
        armature_obj,
        arm_rig_transaction=_arm_rig_transaction,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        compute_effective_parent_matrix=compute_effective_parent_matrix,
        validate_effective_parent_transform=validate_effective_parent_transform,
        world_to_local_position=world_to_local_position,
        apply_target_rotation=apply_target_rotation,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        shoulder_x_offset=SHOULDER_X_OFFSET,
        wrist_rest_z=WRIST_REST_Z,
        elbow_rest_z=ELBOW_REST_Z,
        default_pole_outward_offset=DEFAULT_POLE_OUTWARD_OFFSET,
        default_pole_backward_offset=DEFAULT_POLE_BACKWARD_OFFSET,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: get_arm_ik_state
# PURPOSE: 为 Layer 4 唯一 get_arm_ik_state 实现装配控制器归属核验、依赖图更新及上肢领域配置
# REASON: 彻底移出 arm_ik.py 中的六层内部依赖装配
def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Wired Layer 4 get_arm_ik_state entrypoint."""
    return _layer4_state_query.get_arm_ik_state(
        armature_obj,
        side,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
    )


# [INTRODUCED 2026-11-25T20:42:00+08:00]
# NODE: 10-B / OWNERSHIP-SEPARATION
# FUNCTION: set_hand_ik_target
# PURPOSE: 为 Layer 4 唯一 set_hand_ik_target 实现装配同层预检/自动初始化/状态查询、事务协调器及领域数学与配置
# REASON: 彻底移出 arm_ik.py 中的六层内部依赖装配，保持 Layer 4 层内调用有向无环图 (DAG-02)
def set_hand_ik_target(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    world_xyz: Tuple[float, float, float],
    hand_rotation_deg: Optional[Tuple[float, float, float]] = None,
    pole_world_xyz: Optional[Tuple[float, float, float]] = None,
    clamp_reach: bool = True,
    influence: float = 1.0,
) -> dict:
    """Wired Layer 4 set_hand_ik_target entrypoint."""
    return _layer4_hand_target.set_hand_ik_target(
        armature_obj,
        side,
        world_xyz,
        hand_rotation_deg,
        pole_world_xyz,
        clamp_reach,
        influence,
        preflight_arm_ik_parent_transforms=_preflight_arm_ik_parent_transforms,
        setup_arm_ik=setup_arm_ik,
        get_arm_ik_state=get_arm_ik_state,
        arm_rig_transaction=_arm_rig_transaction,
        require_existing_arm_ik_controller_ownership=(
            _layer3_ctrl_ownership._require_existing_arm_ik_controller_ownership
        ),
        trigger_fault_injection=_fault_injection._trigger_fault_injection,
        depsgraph_update=_layer4_depsgraph._depsgraph_update,
        update_arm_ik_depsgraph=_update_arm_ik_depsgraph,
        world_to_local_position=world_to_local_position,
        world_to_local_rotation_quaternion=world_to_local_rotation_quaternion,
        apply_target_rotation=apply_target_rotation,
        arm_ik_target_names=ARM_IK_TARGET_NAMES,
        arm_pole_target_names=ARM_POLE_TARGET_NAMES,
        arm_ik_constraint_names=ARM_IK_CONSTRAINT_NAMES,
        hand_rot_constraint_names=HAND_ROT_CONSTRAINT_NAMES,
        min_arm_reach=MIN_ARM_REACH,
        max_arm_reach=MAX_ARM_REACH,
        default_pole_outward_offset=DEFAULT_POLE_OUTWARD_OFFSET,
        default_pole_backward_offset=DEFAULT_POLE_BACKWARD_OFFSET,
    )


__all__ = (
    "_apply_single_constraint_target_unit",
    "_arm_rig_transaction",
    "_authorized_assign_constraint_targets",
    "_authorized_assign_object_parent",
    "_authorized_create_constraint",
    "_authorized_link_child_collection",
    "_authorized_link_object_to_collection",
    "_authorized_remove_constraint",
    "_authorized_restore_collection_object_relationships",
    "_authorized_restore_relationship",
    "_authorized_revert_relationship_record",
    "_authorized_unlink_child_collection",
    "_authorized_unlink_object_from_collection",
    "_clear_or_retire_failure_isolation_by_coordinator",
    "_create_arm_rig_transaction_context",
    "_ensure_character_collection",
    "_get_or_create_empty",
    "_issue_coordinator_authorization_grant",
    "_preflight_arm_ik_parent_transforms",
    "_rollback_arm_rig_state",
    "_snapshot_arm_rig_state",
    "_update_arm_ik_depsgraph",
    "_verify_arm_rig_state_restored",
    "_verify_dead_armature_tombstone_retirement_evidence",
    "get_arm_ik_state",
    "request_armature_deisolation",
    "reset_arm_ik",
    "retire_dead_armature_tombstone",
    "set_arm_ik_influence",
    "set_hand_ik_target",
    "setup_arm_ik",
    "verify_armature_deisolation_evidence",
)
