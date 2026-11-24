"""Complete Arm Rig rollback verifier migrated from `src/rig/arm_ik.py` (Task 10-B Layer 5 L5-04)."""

from typing import Any, Callable, Dict, List, Optional, Tuple

import bpy
from mathutils import Euler, Quaternion, Vector


# [INTRODUCED 2026-11-25T00:39:00+08:00]
# NODE: 10-B / L5-04
# FUNCTION: _verify_arm_rig_state_restored
# PURPOSE: 执行原完整回滚结果验证，核验资源身份、数学状态、事务栈及关系日志终态
# REASON: 将回滚执行后的独立核验主节点归入 Layer 5，保持原数学判定、异常传播与 Coordinator 决策边界
def _verify_arm_rig_state_restored(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
    *,
    snapshot_arm_rig_state: Callable[..., Dict[str, Any]],
    active_transaction_stack: List[Any],
    relationship_operation_state_cls: Any,
) -> None:
    """Verify that current Arm IK rig state precisely matches the snapshot.

    Raises:
        RuntimeError: If any discrepancy is detected between current state and snapshot.
    """
    current = snapshot_arm_rig_state(arm)
    diffs: List[str] = []
    TOL = 1e-5

    def _vec_diff(v1, v2) -> float:
        return max(abs(a - b) for a, b in zip(v1, v2))

    def _quat_diff(q1, q2) -> float:
        d1 = sum((a - b)**2 for a, b in zip(q1, q2))**0.5
        d2 = sum((a + b)**2 for a, b in zip(q1, q2))**0.5
        return min(d1, d2)

    def _mat_diff(m1, m2) -> Tuple[float, int, int]:
        max_d = 0.0
        max_r, max_c = 0, 0
        for r in range(4):
            for c in range(4):
                d = abs(m1[r][c] - m2[r][c])
                if d > max_d:
                    max_d = d
                    max_r, max_c = r, c
        return max_d, max_r, max_c

    # 1. Collection check
    s_col = snapshot.get("character_collection", {})
    c_col = current.get("character_collection", {})

    if s_col.get("existed"):
        if not c_col.get("existed"):
            diffs.append("Character collection existed in snapshot but is missing in current state")
        else:
            # Check original collection object identity
            orig_col_ref = s_col.get("col_ref")
            orig_col_ptr = s_col.get("col_ptr")
            curr_col_ref = c_col.get("col_ref")
            curr_col_ptr = c_col.get("col_ptr")

            if orig_col_ref is not None:
                try:
                    live_col_ptr = orig_col_ref.as_pointer()
                    if orig_col_ptr and live_col_ptr != orig_col_ptr:
                        diffs.append("Character collection original pointer changed")
                except ReferenceError:
                    diffs.append("Character collection original collection destroyed")

            if orig_col_ptr and curr_col_ptr and curr_col_ptr != orig_col_ptr:
                diffs.append(f"Character collection identity mismatch: expected={orig_col_ptr}, actual={curr_col_ptr}")

            if orig_col_ref is not None and s_col.get("name") != c_col.get("name"):
                diffs.append(f"Character collection name '{c_col.get('name')}' != expected '{s_col.get('name')}'")

            # Parent / Child / Member identity hierarchy verification
            if s_col.get("children_of_scene") and not c_col.get("children_of_scene"):
                diffs.append("Character collection missing from scene collection children")

            def _live_identity_set(items, desc: str = "item"):
                result = set()
                for item in items:
                    try:
                        result.add(item.as_pointer())
                    except ReferenceError:
                        diffs.append(f"Character collection original {desc} was destroyed")
                return result

            original_parent_ptrs = _live_identity_set(
                s_col.get("parent_refs", []), "parent collection"
            )
            current_parent_ptrs = _live_identity_set(
                c_col.get("parent_refs", []), "current parent collection"
            )
            missing_parent_ptrs = (
                original_parent_ptrs - current_parent_ptrs
            )
            if missing_parent_ptrs:
                diffs.append(
                    "Character collection original parent "
                    f"identities missing: {missing_parent_ptrs}"
                )

            original_child_ptrs = _live_identity_set(
                s_col.get("child_refs", []), "child collection"
            )
            current_child_ptrs = _live_identity_set(
                c_col.get("child_refs", []), "current child collection"
            )
            missing_child_ptrs = (
                original_child_ptrs - current_child_ptrs
            )
            if missing_child_ptrs:
                diffs.append(
                    "Character collection original child "
                    f"identities missing: {missing_child_ptrs}"
                )

            original_obj_ptrs = _live_identity_set(
                s_col.get("object_refs", []), "member object"
            )
            current_obj_ptrs = _live_identity_set(
                c_col.get("object_refs", []), "current member object"
            )
            missing_obj_ptrs = (
                original_obj_ptrs - current_obj_ptrs
            )
            if missing_obj_ptrs:
                diffs.append(
                    "Character collection original member "
                    f"identities missing: {missing_obj_ptrs}"
                )
    else:
        # Snapshot did NOT have Character collection.
        # If active_tx created it, active_tx.created_collections will catch it below if not removed.
        # If an external party created a Character collection, it must be preserved.
        pass

    # Check that transaction-created collections do not linger
    if active_tx is not None:
        for reg in getattr(active_tx, "created_collections", []):
            c_name = reg.get("created_name")
            c_ptr = reg.get("col_ptr")
            c_ref = reg.get("col_ref")
            found_lingering = False
            if c_ref is not None:
                try:
                    if c_ref.name in bpy.data.collections and bpy.data.collections[c_ref.name] == c_ref:
                        found_lingering = True
                except ReferenceError:
                    found_lingering = False
            if not found_lingering and c_name in bpy.data.collections:
                col_obj = bpy.data.collections[c_name]
                if c_ptr is None or col_obj.as_pointer() == c_ptr:
                    found_lingering = True
            if found_lingering:
                diffs.append(f"Transaction-created collection '{c_name}' still exists in scene")

    # 2. Controllers check
    s_ctrls = snapshot.get("controllers", {})
    c_ctrls = current.get("controllers", {})
    for c_name, sc in s_ctrls.items():
        cc = c_ctrls.get(c_name)
        if cc is None or sc["exists"] != cc["exists"]:
            diffs.append(f"Controller {c_name} exists={getattr(cc, 'get', lambda k: None)('exists')}, expected {sc['exists']}")
            continue
        if not sc["exists"]:
            continue

        try:
            obj_mismatch = (sc["obj_ref"] != cc["obj_ref"])
        except ReferenceError:
            obj_mismatch = True
        if obj_mismatch:
            diffs.append(f"Controller {c_name} obj_ref identity mismatch")
        if sc.get("obj_ptr") and cc.get("obj_ptr") and sc["obj_ptr"] != cc["obj_ptr"]:
            diffs.append(f"Controller {c_name} obj_ptr mismatch: {cc['obj_ptr']} != {sc['obj_ptr']}")
        try:
            data_mismatch = (sc["data_ref"] != cc["data_ref"])
        except ReferenceError:
            data_mismatch = True
        if data_mismatch:
            diffs.append(f"Controller {c_name} data_ref identity mismatch")
        if sc.get("data_ptr") and cc.get("data_ptr") and sc["data_ptr"] != cc["data_ptr"]:
            diffs.append(f"Controller {c_name} data_ptr mismatch: {cc['data_ptr']} != {sc['data_ptr']}")
        if sc["obj_name"] != cc["obj_name"]:
            diffs.append(f"Controller {c_name} obj_name {cc['obj_name']} != {sc['obj_name']}")
        if sc["type"] != cc["type"]:
            diffs.append(f"Controller {c_name} type {cc['type']} != {sc['type']}")
        if sc["parent"] != cc["parent"]:
            diffs.append(f"Controller {c_name} parent {cc['parent']} != {sc['parent']}")

        mat_inv_diff, mr, mc = _mat_diff(sc["matrix_parent_inverse"], cc["matrix_parent_inverse"])
        if mat_inv_diff > TOL:
            diffs.append(f"Controller {c_name} matrix_parent_inverse[{mr}][{mc}] diff {mat_inv_diff:.6e} > {TOL}")

        loc_diff = _vec_diff(sc["location"], cc["location"])
        if loc_diff > TOL:
            diffs.append(f"Controller {c_name} location diff {loc_diff:.6e} > {TOL}")

        if sc["rotation_mode"] != cc["rotation_mode"]:
            diffs.append(f"Controller {c_name} rotation_mode {cc['rotation_mode']} != {sc['rotation_mode']}")

        euler_diff = _vec_diff(sc["rotation_euler"], cc["rotation_euler"])
        if euler_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_euler diff {euler_diff:.6e} > {TOL}")

        quat_diff = _quat_diff(sc["rotation_quaternion"], cc["rotation_quaternion"])
        if quat_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_quaternion diff {quat_diff:.6e} > {TOL}")

        d_angle = abs(sc["rotation_axis_angle"][0] - cc["rotation_axis_angle"][0])
        d_axis = _vec_diff(sc["rotation_axis_angle"][1:], cc["rotation_axis_angle"][1:])
        axis_diff = max(d_angle, d_axis)
        if axis_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_axis_angle diff {axis_diff:.6e} > {TOL}")

        scale_diff = _vec_diff(sc["scale"], cc["scale"])
        if scale_diff > TOL:
            diffs.append(f"Controller {c_name} scale diff {scale_diff:.6e} > {TOL}")

        mat_w_diff, wr, wc = _mat_diff(sc["matrix_world"], cc["matrix_world"])
        if mat_w_diff > TOL:
            diffs.append(f"Controller {c_name} matrix_world[{wr}][{wc}] diff {mat_w_diff:.6e} > {TOL}")

        if set(sc["collections"]) != set(cc["collections"]):
            diffs.append(f"Controller {c_name} collections {cc['collections']} != {sc['collections']}")

        if sc["type"] == "EMPTY":
            if sc["empty_display_type"] != cc["empty_display_type"]:
                diffs.append(f"Controller {c_name} empty_display_type {cc['empty_display_type']} != {sc['empty_display_type']}")
            if abs(sc["empty_display_size"] - cc["empty_display_size"]) > TOL:
                diffs.append(f"Controller {c_name} empty_display_size {cc['empty_display_size']} != {sc['empty_display_size']}")

    # 3. Pose bones check
    s_bones = snapshot.get("pose_bones", {})
    c_bones = current.get("pose_bones", {})
    for b_name, sb in s_bones.items():
        cb = c_bones.get(b_name)
        if cb is None:
            diffs.append(f"Pose bone {b_name} missing in current state")
            continue

        loc_diff = _vec_diff(sb["location"], cb["location"])
        if loc_diff > TOL:
            diffs.append(f"Bone {b_name} location diff {loc_diff:.6e} > {TOL}")

        if sb["rotation_mode"] != cb["rotation_mode"]:
            diffs.append(f"Bone {b_name} rotation_mode {cb['rotation_mode']} != {sb['rotation_mode']}")

        euler_diff = _vec_diff(sb["rotation_euler"], cb["rotation_euler"])
        if euler_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_euler diff {euler_diff:.6e} > {TOL}")

        quat_diff = _quat_diff(sb["rotation_quaternion"], cb["rotation_quaternion"])
        if quat_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_quaternion diff {quat_diff:.6e} > {TOL}")

        d_angle = abs(sb["rotation_axis_angle"][0] - cb["rotation_axis_angle"][0])
        d_axis = _vec_diff(sb["rotation_axis_angle"][1:], cb["rotation_axis_angle"][1:])
        axis_diff = max(d_angle, d_axis)
        if axis_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_axis_angle diff {axis_diff:.6e} > {TOL}")

        scale_diff = _vec_diff(sb["scale"], cb["scale"])
        if scale_diff > TOL:
            diffs.append(f"Bone {b_name} scale diff {scale_diff:.6e} > {TOL}")

        basis_diff, br, bc = _mat_diff(sb["matrix_basis"], cb["matrix_basis"])
        if basis_diff > TOL:
            diffs.append(f"Bone {b_name} matrix_basis[{br}][{bc}] diff {basis_diff:.6e} > {TOL}")

        for axis in ("x", "y", "z"):
            if sb[f"lock_ik_{axis}"] != cb[f"lock_ik_{axis}"]:
                diffs.append(f"Bone {b_name} lock_ik_{axis} {cb[f'lock_ik_{axis}']} != {sb[f'lock_ik_{axis}']}")
            if sb[f"use_ik_limit_{axis}"] != cb[f"use_ik_limit_{axis}"]:
                diffs.append(f"Bone {b_name} use_ik_limit_{axis} {cb[f'use_ik_limit_{axis}']} != {sb[f'use_ik_limit_{axis}']}")
            if abs(sb[f"ik_min_{axis}"] - cb[f"ik_min_{axis}"]) > TOL:
                diffs.append(f"Bone {b_name} ik_min_{axis} {cb[f'ik_min_{axis}']} != {sb[f'ik_min_{axis}']}")
            if abs(sb[f"ik_max_{axis}"] - cb[f"ik_max_{axis}"]) > TOL:
                diffs.append(f"Bone {b_name} ik_max_{axis} {cb[f'ik_max_{axis}']} != {sb[f'ik_max_{axis}']}")

        # Constraints
        sc_list = sb["constraints"]
        cc_list = cb["constraints"]

        # Check that transaction-created constraints do not linger
        if active_tx is not None:
            for reg_con in getattr(active_tx, "created_constraints", []):
                if reg_con.get("bone_name") == b_name:
                    expected_ptr = reg_con.get("con_ptr")
                    for c in cc_list:
                        if c.get("con_ptr") == expected_ptr:
                            diffs.append(
                                f"Bone {b_name} transaction-created constraint "
                                f"'{reg_con.get('created_name')}' still present after rollback"
                            )

        # Map current live constraints by pointer
        cc_by_ptr = {c.get("con_ptr"): c for c in cc_list if c.get("con_ptr")}
        orig_ptrs = [sc["con_ptr"] for sc in sc_list if sc.get("con_ptr")]

        # Verify each original constraint is restored
        for idx, sc in enumerate(sc_list):
            orig_con = sc.get("con_ref")
            orig_ptr = sc.get("con_ptr")
            label = f"Bone {b_name} constraint[{idx}] '{sc['name']}'"

            if orig_con is None or orig_ptr is None:
                diffs.append(f"{label}: snapshot identity missing")
                continue

            try:
                live_orig_ptr = orig_con.as_pointer()
            except ReferenceError:
                diffs.append(f"{label}: original constraint destroyed")
                continue

            if live_orig_ptr != orig_ptr:
                diffs.append(f"{label}: original pointer changed")
                continue

            cc = cc_by_ptr.get(orig_ptr)
            if cc is None:
                diffs.append(f"{label}: identity mismatch: original constraint destroyed or absent from live chain")
                continue

            curr_con = cc.get("con_ref")
            curr_ptr = cc.get("con_ptr")
            if curr_con is None or curr_ptr is None:
                diffs.append(f"{label}: current identity missing")
                continue

            if curr_ptr != orig_ptr:
                diffs.append(
                    f"{label}: identity mismatch; "
                    f"expected={orig_ptr}, "
                    f"actual={curr_ptr}"
                )

            if sc["name"] != cc["name"]:
                diffs.append(f"{label} name {cc['name']} != {sc['name']}")
            if sc["type"] != cc["type"]:
                diffs.append(f"{label} type {cc['type']} != {sc['type']}")
            if abs(sc["influence"] - cc["influence"]) > TOL:
                diffs.append(f"{label} influence {cc['influence']} != {sc['influence']}")
            if sc["mute"] != cc["mute"]:
                diffs.append(f"{label} mute {cc['mute']} != {sc['mute']}")
            if sc.get("target") != cc.get("target"):
                diffs.append(f"{label} target {cc.get('target')} != {sc.get('target')}")
            if sc.get("subtarget") != cc.get("subtarget"):
                diffs.append(f"{label} subtarget {cc.get('subtarget')} != {sc.get('subtarget')}")
            if sc.get("pole_target") != cc.get("pole_target"):
                diffs.append(f"{label} pole_target {cc.get('pole_target')} != {sc.get('pole_target')}")
            if sc.get("pole_subtarget") != cc.get("pole_subtarget"):
                diffs.append(f"{label} pole_subtarget {cc.get('pole_subtarget')} != {sc.get('pole_subtarget')}")

            if sc["type"] == "IK":
                if sc.get("chain_count") != cc.get("chain_count"):
                    diffs.append(f"{label} chain_count {cc.get('chain_count')} != {sc.get('chain_count')}")
                if sc.get("use_tail") != cc.get("use_tail"):
                    diffs.append(f"{label} use_tail {cc.get('use_tail')} != {sc.get('use_tail')}")
                if sc.get("use_stretch") != cc.get("use_stretch"):
                    diffs.append(f"{label} use_stretch {cc.get('use_stretch')} != {sc.get('use_stretch')}")
                if abs(sc.get("pole_angle", 0.0) - cc.get("pole_angle", 0.0)) > TOL:
                    diffs.append(f"{label} pole_angle {cc.get('pole_angle')} != {sc.get('pole_angle')}")
                if sc.get("iterations") != cc.get("iterations"):
                    diffs.append(f"{label} iterations {cc.get('iterations')} != {sc.get('iterations')}")
            elif sc["type"] == "COPY_ROTATION":
                if sc.get("target_space") != cc.get("target_space"):
                    diffs.append(f"{label} target_space {cc.get('target_space')} != {sc.get('target_space')}")
                if sc.get("owner_space") != cc.get("owner_space"):
                    diffs.append(f"{label} owner_space {cc.get('owner_space')} != {sc.get('owner_space')}")
                if sc.get("mix_mode") != cc.get("mix_mode"):
                    diffs.append(f"{label} mix_mode {cc.get('mix_mode')} != {sc.get('mix_mode')}")
                for axis in ("x", "y", "z"):
                    if sc.get(f"use_{axis}") != cc.get(f"use_{axis}"):
                        diffs.append(f"{label} use_{axis} {cc.get(f'use_{axis}')} != {sc.get(f'use_{axis}')}")
                    if sc.get(f"invert_{axis}") != cc.get(f"invert_{axis}"):
                        diffs.append(f"{label} invert_{axis} {cc.get(f'invert_{axis}')} != {sc.get(f'invert_{axis}')}")
                if sc.get("use_offset") != cc.get("use_offset"):
                    diffs.append(f"{label} use_offset {cc.get('use_offset')} != {sc.get('use_offset')}")

            # Check generic properties
            s_gen = sc.get("generic_props", {})
            c_gen = cc.get("generic_props", {})
            for g_prop, s_val in s_gen.items():
                c_val = c_gen.get(g_prop)
                if isinstance(s_val, (Vector, Euler)):
                    if c_val is None or _vec_diff(s_val, c_val) > TOL:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")
                elif isinstance(s_val, Quaternion):
                    if c_val is None or _quat_diff(s_val, c_val) > TOL:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")
                elif isinstance(s_val, tuple):
                    if c_val is None or not hasattr(c_val, "__len__") or len(c_val) != len(s_val):
                        diffs.append(f"{label} {g_prop} length mismatch: {c_val} != {s_val}")
                    else:
                        for arr_i, (sv, cv) in enumerate(zip(s_val, c_val)):
                            if isinstance(sv, float):
                                if abs(sv - cv) > TOL:
                                    diffs.append(f"{label} {g_prop}[{arr_i}] {cv} != {sv} (diff {abs(sv - cv):.6e} > {TOL})")
                            elif sv != cv:
                                diffs.append(f"{label} {g_prop}[{arr_i}] {cv} != {sv}")
                elif isinstance(s_val, float):
                    if c_val is None or abs(s_val - c_val) > TOL:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")
                else:
                    if s_val != c_val:
                        diffs.append(f"{label} {g_prop} {c_val} != {s_val}")

        # Check relative ordering of original constraints
        orig_live_indices = []
        for sc in sc_list:
            sc_ptr = sc.get("con_ptr")
            for c_idx, cc in enumerate(cc_list):
                if cc.get("con_ptr") == sc_ptr:
                    orig_live_indices.append(c_idx)
                    break
        if orig_live_indices != sorted(orig_live_indices):
            diffs.append(
                f"Bone {b_name} original constraints relative order violated: "
                f"indices={orig_live_indices}"
            )

        # In standalone check without transaction context, constraint count must match exactly
        if active_tx is None and len(sc_list) != len(cc_list):
            diffs.append(f"Bone {b_name} constraint count {len(cc_list)} != {len(sc_list)}")

    # 4. Active transaction stack check
    if active_tx is None:
        if len(active_transaction_stack) != 0:
            diffs.append(f"Active transaction stack is not empty (contains {len(active_transaction_stack)} transactions)")
    else:
        if active_transaction_stack != [active_tx]:
            diffs.append(f"Active transaction stack contains unexpected transactions: {active_transaction_stack}")

    # 5. Relationship operation log terminal state verification (Task 10-B-11)
    if active_tx is not None:
        for op_rec in getattr(active_tx, "prepared_relationship_mutations", []):
            op_id = op_rec.get("operation_id", "<unknown>")
            op_state = op_rec.get("operation_state")
            if op_state == relationship_operation_state_cls.RECOVERY_UNCERTAIN:
                diffs.append(
                    f"Relationship operation '{op_id}' is in RECOVERY_UNCERTAIN state after rollback"
                )
            elif op_state not in (
                relationship_operation_state_cls.NO_EFFECT,
                relationship_operation_state_cls.REVERTED,
            ):
                diffs.append(
                    f"Relationship operation '{op_id}' did not reach a valid rollback terminal state "
                    f"(expected NO_EFFECT or REVERTED, got {op_state})"
                )

    if diffs:
        raise RuntimeError("Arm rig rollback verification failed: " + "; ".join(diffs))