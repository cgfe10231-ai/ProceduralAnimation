from typing import Any, Callable, Dict, List, Optional, Tuple

import bpy

from src.scene_transaction_integrity.layer5.value_evidence import (
    _clone_snapshot_property_value,
    _freeze_fingerprint_property_value,
)


def _capture_pre_snapshot_structural_fingerprint(
    arm: bpy.types.Object,
    *,
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    required_arm_ik_bone_names: Tuple[str, ...],
) -> Dict[str, Any]:
    """Capture a comprehensive read-only unrounded structural and value fingerprint before SNAPSHOTTING."""
    char_col = bpy.data.collections.get("Character")
    scene_children = bpy.context.scene.collection.children if (bpy.context and bpy.context.scene) else []
    char_col_fp = None
    if char_col is not None:
        char_col_fp = {
            "col_ptr": int(char_col.as_pointer()),
            "name": str(char_col.name),
            "children_of_scene": bool(char_col.name in scene_children),
            "parent_ptrs": tuple(sorted(p.as_pointer() for p in bpy.data.collections if any(ch.as_pointer() == char_col.as_pointer() for ch in p.children))),
            "child_ptrs": tuple(sorted(ch.as_pointer() for ch in char_col.children)),
            "object_ptrs": tuple(sorted(o.as_pointer() for o in char_col.objects)),
            "object_names": tuple(sorted(str(o.name) for o in char_col.objects)),
        }

    ctrl_names = (
        arm_ik_target_names["L"],
        arm_ik_target_names["R"],
        arm_pole_target_names["L"],
        arm_pole_target_names["R"],
    )
    ctrls_fp: Dict[str, Any] = {}
    for c_name in ctrl_names:
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is None:
            ctrls_fp[c_name] = None
        else:
            ctrls_fp[c_name] = {
                "obj_ptr": int(c_obj.as_pointer()),
                "data_ptr": int(c_obj.data.as_pointer()) if getattr(c_obj, "data", None) is not None else None,
                "name": str(c_obj.name),
                "type": str(c_obj.type),
                "parent_ptr": int(c_obj.parent.as_pointer()) if c_obj.parent is not None else None,
                "matrix_parent_inverse": tuple(tuple(float(v) for v in row) for row in c_obj.matrix_parent_inverse),
                "location": tuple(float(v) for v in c_obj.location),
                "rotation_mode": str(c_obj.rotation_mode),
                "rotation_euler": tuple(float(v) for v in c_obj.rotation_euler),
                "rotation_quaternion": tuple(float(v) for v in c_obj.rotation_quaternion),
                "rotation_axis_angle": tuple(float(v) for v in c_obj.rotation_axis_angle),
                "scale": tuple(float(v) for v in c_obj.scale),
                "matrix_world": tuple(tuple(float(v) for v in row) for row in c_obj.matrix_world),
                "empty_display_type": getattr(c_obj, "empty_display_type", None) if c_obj.type == "EMPTY" else None,
                "empty_display_size": float(getattr(c_obj, "empty_display_size", 0.0)) if (c_obj.type == "EMPTY" and getattr(c_obj, "empty_display_size", None) is not None) else None,
                "users_collection_ptrs": tuple(sorted(c.as_pointer() for c in c_obj.users_collection)),
                "users_collection_names": tuple(sorted(str(c.name) for c in c_obj.users_collection)),
            }

    bones_fp: Dict[str, Any] = {}
    present_arm_bones: List[str] = []
    for b_name in required_arm_ik_bone_names:
        pbone = arm.pose.bones.get(b_name) if getattr(arm, "pose", None) else None
        if pbone is None:
            bones_fp[b_name] = None
            continue
        present_arm_bones.append(b_name)
        con_list: List[Dict[str, Any]] = []
        for con in pbone.constraints:
            c_dict: Dict[str, Any] = {
                "con_ptr": int(con.as_pointer()),
                "name": str(con.name),
                "type": str(con.type),
                "influence": float(con.influence),
                "mute": bool(con.mute),
                "target_ptr": int(con.target.as_pointer()) if getattr(con, "target", None) is not None else None,
                "subtarget": str(getattr(con, "subtarget", "")),
                "pole_target_ptr": int(con.pole_target.as_pointer()) if getattr(con, "pole_target", None) is not None else None,
                "pole_subtarget": str(getattr(con, "pole_subtarget", "")),
            }
            if con.type == "IK":
                c_dict.update({
                    "chain_count": int(getattr(con, "chain_count", 0)),
                    "use_tail": bool(getattr(con, "use_tail", True)),
                    "use_stretch": bool(getattr(con, "use_stretch", False)),
                    "pole_angle": float(getattr(con, "pole_angle", 0.0)),
                    "iterations": int(getattr(con, "iterations", 500)),
                })
            elif con.type == "COPY_ROTATION":
                c_dict.update({
                    "target_space": str(getattr(con, "target_space", "WORLD")),
                    "owner_space": str(getattr(con, "owner_space", "WORLD")),
                    "mix_mode": str(getattr(con, "mix_mode", "REPLACE")),
                    "use_x": bool(getattr(con, "use_x", True)),
                    "use_y": bool(getattr(con, "use_y", True)),
                    "use_z": bool(getattr(con, "use_z", True)),
                    "invert_x": bool(getattr(con, "invert_x", False)),
                    "invert_y": bool(getattr(con, "invert_y", False)),
                    "invert_z": bool(getattr(con, "invert_z", False)),
                    "use_offset": bool(getattr(con, "use_offset", False)),
                })

            generic_props: Dict[str, Any] = {}
            for p in con.rna_type.properties:
                if not p.is_readonly and p.identifier not in ("rna_type", "name", "mute", "influence"):
                    try:
                        val = getattr(con, p.identifier)
                        cloned = _clone_snapshot_property_value(val)
                        generic_props[p.identifier] = _freeze_fingerprint_property_value(cloned)
                    except BaseException as exc:
                        raise RuntimeError(
                            "FINGERPRINT_PROPERTY_CAPTURE_FAILED: "
                            f"bone={pbone.name}, "
                            f"constraint={con.name}, "
                            f"type={con.type}, "
                            f"property={p.identifier}, "
                            f"cause={type(exc).__name__}: {exc}"
                        ) from exc
            c_dict["generic_props"] = generic_props
            con_list.append(c_dict)

        bones_fp[b_name] = {
            "location": tuple(float(v) for v in pbone.location),
            "rotation_mode": str(pbone.rotation_mode),
            "rotation_euler": tuple(float(v) for v in pbone.rotation_euler),
            "rotation_quaternion": tuple(float(v) for v in pbone.rotation_quaternion),
            "rotation_axis_angle": tuple(float(v) for v in pbone.rotation_axis_angle),
            "scale": tuple(float(v) for v in pbone.scale),
            "matrix_basis": tuple(tuple(float(v) for v in row) for row in pbone.matrix_basis),
            "lock_ik_x": bool(pbone.lock_ik_x),
            "lock_ik_y": bool(pbone.lock_ik_y),
            "lock_ik_z": bool(pbone.lock_ik_z),
            "use_ik_limit_x": bool(pbone.use_ik_limit_x),
            "use_ik_limit_y": bool(pbone.use_ik_limit_y),
            "use_ik_limit_z": bool(pbone.use_ik_limit_z),
            "ik_min_x": float(pbone.ik_min_x),
            "ik_max_x": float(pbone.ik_max_x),
            "ik_min_y": float(pbone.ik_min_y),
            "ik_max_y": float(pbone.ik_max_y),
            "ik_min_z": float(pbone.ik_min_z),
            "ik_max_z": float(pbone.ik_max_z),
            "constraints": tuple(con_list),
        }

    return {
        "arm_ptr": int(arm.as_pointer()),
        "arm_name": str(arm.name),
        "data_ptr": int(arm.data.as_pointer()) if getattr(arm, "data", None) is not None else None,
        "total_pose_bone_count": len(arm.pose.bones) if getattr(arm, "pose", None) else 0,
        "present_arm_bones": tuple(present_arm_bones),
        "character_collection": char_col_fp,
        "controllers": ctrls_fp,
        "pose_bones": bones_fp,
        "all_object_ptrs": frozenset(int(o.as_pointer()) for o in bpy.data.objects),
        "all_collection_ptrs": frozenset(int(c.as_pointer()) for c in bpy.data.collections),
    }


def _snapshot_arm_rig_state(
    arm: bpy.types.Object,
    *,
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    active_transaction_stack: List[Any],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    depsgraph_update: Callable[[], None],
    find_live_object_by_identity: Callable[[Any, int], Optional[bpy.types.Object]],
) -> Dict[str, Any]:
    """Capture full production state snapshot of Arm IK controllers, pose bones, constraints, and collections.

    Zero-mutation guarantee: Strictly inspects and copies properties without modifying Blender state.
    """
    trigger_fault_injection(
        "during_snapshot_creation",
        {
            "arm": arm,
            "tx": (active_transaction_stack[-1] if active_transaction_stack else None),
        },
    )
    depsgraph_update()

    # 1. Collections snapshot
    char_col = bpy.data.collections.get("Character")
    scene_children = bpy.context.scene.collection.children if bpy.context.scene else []
    char_col_data = {
        "existed": char_col is not None,
        "col_ref": char_col,
        "col_ptr": char_col.as_pointer() if (char_col is not None and hasattr(char_col, "as_pointer")) else None,
        "name": char_col.name if char_col is not None else None,
        "children_of_scene": (char_col is not None and char_col.name in scene_children),
        "parent_collections": [c.name for c in bpy.data.collections if char_col is not None and char_col.name in c.children],
        "child_collections": [c.name for c in char_col.children] if char_col is not None else [],
        "object_names": set(char_col.objects.keys()) if char_col is not None else set(),
        "parent_refs": [
            parent
            for parent in bpy.data.collections
            if char_col is not None
            and any(child.as_pointer() == char_col.as_pointer() for child in parent.children)
        ],
        "parent_ptrs": [
            parent.as_pointer()
            for parent in bpy.data.collections
            if char_col is not None
            and any(child.as_pointer() == char_col.as_pointer() for child in parent.children)
            and hasattr(parent, "as_pointer")
        ],
        "child_refs": (
            list(char_col.children)
            if char_col is not None
            else []
        ),
        "child_ptrs": [
            child.as_pointer()
            for child in (list(char_col.children) if char_col is not None else [])
            if hasattr(child, "as_pointer")
        ],
        "object_refs": (
            list(char_col.objects)
            if char_col is not None
            else []
        ),
    }

    # 2. Controllers snapshot (HandIK.L/R, ElbowPole.L/R)
    ctrl_names = (
        arm_ik_target_names["L"],
        arm_ik_target_names["R"],
        arm_pole_target_names["L"],
        arm_pole_target_names["R"],
    )
    controllers_data: Dict[str, Dict[str, Any]] = {}
    for c_name in ctrl_names:
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is None:
            controllers_data[c_name] = {"exists": False}
        else:
            controllers_data[c_name] = {
                "exists": True,
                "obj_ref": c_obj,
                "obj_ptr": c_obj.as_pointer() if hasattr(c_obj, "as_pointer") else None,
                "data_ref": getattr(c_obj, "data", None),
                "data_ptr": c_obj.data.as_pointer() if getattr(c_obj, "data", None) and hasattr(c_obj.data, "as_pointer") else None,
                "obj_name": c_obj.name,
                "type": c_obj.type,
                "parent": c_obj.parent,
                "parent_ptr": c_obj.parent.as_pointer() if c_obj.parent is not None and hasattr(c_obj.parent, "as_pointer") else None,
                "matrix_parent_inverse": c_obj.matrix_parent_inverse.copy(),
                "location": c_obj.location.copy(),
                "rotation_mode": c_obj.rotation_mode,
                "rotation_euler": c_obj.rotation_euler.copy(),
                "rotation_quaternion": c_obj.rotation_quaternion.copy(),
                "rotation_axis_angle": tuple(c_obj.rotation_axis_angle),
                "scale": c_obj.scale.copy(),
                "matrix_world": c_obj.matrix_world.copy(),
                "empty_display_type": getattr(c_obj, "empty_display_type", None) if c_obj.type == "EMPTY" else None,
                "empty_display_size": getattr(c_obj, "empty_display_size", None) if c_obj.type == "EMPTY" else None,
                "collections": [c.name for c in c_obj.users_collection],
                "collection_refs": list(c_obj.users_collection),
                "collection_ptrs": [
                    c.as_pointer()
                    for c in c_obj.users_collection
                    if hasattr(c, "as_pointer")
                ],
            }

    # 3. Pose bones snapshot (upper_arm, forearm, hand across L and R)
    bone_names = (
        "upper_arm.L", "upper_arm.R",
        "forearm.L", "forearm.R",
        "hand.L", "hand.R",
    )
    pose_bones_data: Dict[str, Dict[str, Any]] = {}
    for b_name in bone_names:
        pbone = arm.pose.bones.get(b_name)
        if pbone is None:
            continue

        con_list: List[Dict[str, Any]] = []
        for con in pbone.constraints:
            c_dict: Dict[str, Any] = {
                "name": con.name,
                "type": con.type,
                "con_ref": con,
                "con_ptr": con.as_pointer() if hasattr(con, "as_pointer") else None,
                "influence": float(con.influence),
                "mute": bool(con.mute),
                "target": getattr(con, "target", None),
                "subtarget": getattr(con, "subtarget", ""),
                "pole_target": getattr(con, "pole_target", None),
                "pole_subtarget": getattr(con, "pole_subtarget", ""),
            }
            # Save original Blender Object identity while the snapshot is taken.
            # A later live pointer lookup alone cannot prove the original target.
            for target_field in ("target", "pole_target"):
                original_target = c_dict[target_field]
                if original_target is None:
                    c_dict[f"{target_field}_ptr"] = None
                    continue
                try:
                    original_target_ptr = int(original_target.as_pointer())
                except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"Constraint snapshot identity unreadable: {pbone.name}/{con.name}/{target_field}"
                    ) from exc
                if (original_target_ptr <= 0
                        or find_live_object_by_identity(original_target, original_target_ptr) is None):
                    raise RuntimeError(
                        f"Constraint snapshot target identity unverified: {pbone.name}/{con.name}/{target_field}"
                    )
                c_dict[f"{target_field}_ptr"] = original_target_ptr
            if con.type == "IK":
                c_dict.update({
                    "chain_count": getattr(con, "chain_count", 0),
                    "use_tail": getattr(con, "use_tail", True),
                    "use_stretch": getattr(con, "use_stretch", False),
                    "pole_angle": float(getattr(con, "pole_angle", 0.0)),
                    "iterations": getattr(con, "iterations", 500),
                })
            elif con.type == "COPY_ROTATION":
                c_dict.update({
                    "target_space": getattr(con, "target_space", "WORLD"),
                    "owner_space": getattr(con, "owner_space", "WORLD"),
                    "mix_mode": getattr(con, "mix_mode", "REPLACE"),
                    "use_x": getattr(con, "use_x", True),
                    "use_y": getattr(con, "use_y", True),
                    "use_z": getattr(con, "use_z", True),
                    "invert_x": getattr(con, "invert_x", False),
                    "invert_y": getattr(con, "invert_y", False),
                    "invert_z": getattr(con, "invert_z", False),
                    "use_offset": getattr(con, "use_offset", False),
                })

            generic_props: Dict[str, Any] = {}
            for p in con.rna_type.properties:
                if not p.is_readonly and p.identifier not in ("rna_type", "name", "mute", "influence"):
                    try:
                        val = getattr(con, p.identifier)
                    except Exception as pe:
                        raise RuntimeError(
                            f"Snapshot failed: cannot read property '{p.identifier}' (type {p.type}) "
                            f"on constraint '{con.name}' ({con.type}) on bone '{pbone.name}': {pe}"
                        ) from pe
                    generic_props[p.identifier] = _clone_snapshot_property_value(val)

            c_dict["generic_props"] = generic_props
            con_list.append(c_dict)

        pose_bones_data[b_name] = {
            "name": b_name,
            "location": pbone.location.copy(),
            "rotation_mode": pbone.rotation_mode,
            "rotation_euler": pbone.rotation_euler.copy(),
            "rotation_quaternion": pbone.rotation_quaternion.copy(),
            "rotation_axis_angle": tuple(pbone.rotation_axis_angle),
            "scale": pbone.scale.copy(),
            "matrix_basis": pbone.matrix_basis.copy(),
            "lock_ik_x": bool(pbone.lock_ik_x),
            "lock_ik_y": bool(pbone.lock_ik_y),
            "lock_ik_z": bool(pbone.lock_ik_z),
            "use_ik_limit_x": bool(pbone.use_ik_limit_x),
            "use_ik_limit_y": bool(pbone.use_ik_limit_y),
            "use_ik_limit_z": bool(pbone.use_ik_limit_z),
            "ik_min_x": float(pbone.ik_min_x),
            "ik_max_x": float(pbone.ik_max_x),
            "ik_min_y": float(pbone.ik_min_y),
            "ik_max_y": float(pbone.ik_max_y),
            "ik_min_z": float(pbone.ik_min_z),
            "ik_max_z": float(pbone.ik_max_z),
            "constraints": con_list,
        }

    return {
        "character_collection": char_col_data,
        "controllers": controllers_data,
        "pose_bones": pose_bones_data,
    }


# [INTRODUCED 2026-11-25T00:14:00+08:00]
# NODE: 10-B / L5-02
# FUNCTION: _verify_pre_write_zero_mutation_and_integrity
# PURPOSE: 验证完整快照建立前的事务零写入及结构完整性，向 Coordinator 返回原有证据报告
# REASON: 将快照阶段首次触发的异常完整性验证主节点归入 Layer 5，保持失败分类与状态决策权归属于 Layer 1
def _verify_pre_write_zero_mutation_and_integrity(
    arm: bpy.types.Object,
    pre_fp: Optional[Dict[str, Any]],
    tx: Any,
    *,
    transaction_state_cls: Any,
    capture_pre_snapshot_structural_fingerprint: Callable[..., Dict[str, Any]],
    has_nan_or_inf: Callable[[Any], bool],
    required_arm_ik_bone_names: Tuple[str, ...],
) -> Dict[str, Any]:
    """Layer 5: Verify zero mutations and structural integrity when a transaction aborts before ACTIVE."""
    reasons: List[str] = []

    # 1. Verification of Transaction Execution Phase
    if getattr(tx, "pre_write_integrity_compromised", False):
        extra = getattr(tx, "pre_write_integrity_reasons", [])
        reasons.extend(extra if extra else ["Transaction pre-write integrity explicitly marked compromised"])

    if tx.snapshot is not None:
        reasons.append("Transaction captured full snapshot; cannot be verified via pre-snapshot zero-mutation path")

    if tx.state not in (
        transaction_state_cls.CREATED,
        transaction_state_cls.SNAPSHOTTING,
        transaction_state_cls.FAILED,
    ):
        reasons.append(
            f"Transaction reached post-snapshot execution state '{tx.state.value}'; "
            "cannot be verified as FAILED-A pre-write abort"
        )

    if (
        tx.created_controller_objects
        or tx.created_constraints
        or tx.created_collection_links
        or tx.prepared_relationship_mutations
        or tx.stashed_objects
        or tx.stashed_constraints
        or tx.created_collections
    ):
        reasons.append("Transaction recorded resource or relationship mutations before reaching ACTIVE")

    if pre_fp is None:
        reasons.append("Pre-snapshot structural fingerprint is missing")
        return {"is_verified": False, "reasons": reasons}

    try:
        post_fp = capture_pre_snapshot_structural_fingerprint(arm)
    except BaseException as exc:
        reasons.append(f"Failed to capture post-exception structural fingerprint: {exc}")
        return {"is_verified": False, "reasons": reasons}

    # 2. A failed finiteness check is untrusted evidence, not a verified clean state.
    try:
        nonfinite = has_nan_or_inf(pre_fp) or has_nan_or_inf(post_fp)
    except BaseException as scan_exc:
        reasons.append(
            f"Pre-write fingerprint finiteness could not be verified: "
            f"{type(scan_exc).__name__}: {scan_exc}"
        )
    else:
        if nonfinite:
            reasons.append("Pre-write structural fingerprint contains NaN or Infinite floating point values")

    # 3. Check for missing bones
    if post_fp.get("total_pose_bone_count", 0) > 0:
        missing_bones = [
            b for b in required_arm_ik_bone_names
            if b not in post_fp.get("present_arm_bones", ())
        ]
        if missing_bones:
            reasons.append(f"Required upper-limb pose bones missing: {missing_bones}")

    # 4. Compare every key in fingerprint for exact unrounded equality
    for key in (
        "arm_ptr",
        "arm_name",
        "data_ptr",
        "total_pose_bone_count",
        "present_arm_bones",
        "character_collection",
        "controllers",
        "pose_bones",
        "all_object_ptrs",
        "all_collection_ptrs",
    ):
        pre_val = pre_fp.get(key)
        post_val = post_fp.get(key)
        if pre_val != post_val:
            reasons.append(f"Pre-write state mutated during SNAPSHOTTING in field '{key}'")

    return {
        "is_verified": len(reasons) == 0,
        "reasons": reasons,
    }
