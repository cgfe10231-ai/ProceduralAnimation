"""Arm IK bilateral setup operation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-05)."""

import math
from typing import Any, Callable, Dict, List, Optional

import bpy
from mathutils import Euler, Vector

from src.scene_transaction_integrity.layer3 import ExternalControllerNameConflictError
from src.scene_transaction_integrity.layer4.armature_ops import (
    _apply_arm_ik_prebend_hint_side,
    _resolve_armature,
)
from src.scene_transaction_integrity.layer4.validation import _validate_influence


def setup_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    initial_influence: float = 0.0,
    *,
    arm_rig_transaction: Callable[..., Any],
    assert_arm_rig_cleanup_gate: Callable[..., None],
    assert_arm_rig_failed_isolation_gate: Callable[..., None],
    active_transaction_stack: List[Any],
    managed_armature_identities: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Any],
    armature_isolation_state: Any,
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    verify_transaction_wrong_type_object_ownership: Callable[..., bool],
    ensure_character_collection: Callable[[], Any],
    get_or_create_empty: Callable[..., Any],
    authorized_create_constraint: Callable[..., Any],
    authorized_assign_constraint_targets: Callable[..., None],
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
    uuid4: Callable[[], Any],
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    arm_ik_constraint_names: Dict[str, str],
    hand_rot_constraint_names: Dict[str, str],
    shoulder_x_offset: float,
    wrist_rest_z: float,
    elbow_rest_z: float,
    default_pole_outward_offset: float,
    default_pole_backward_offset: float,
) -> Dict[str, bpy.types.Object]:
    """Configure native Blender two-bone arm IK chains, elbow pole targets, and hand orientation controls.

    This function is strictly idempotent:
    - Preserves existing controller objects, parents, matrices, positions, orientations, and rotation modes.
    - Preserves existing constraint instances, configurations, and active influences.
    - Only initializes neutral rest positions when creating brand new controllers.
    - Only sets initial_influence when creating brand new constraints.
    - Only applies pre-bend hints when initializing a previously unconstrained arm.

    Args:
        armature_obj: Optional CharacterArmature object.
        initial_influence: Initial constraint influence in [0.0, 1.0]. Defaults to 0.0 (FK mode).

    Returns:
        Dict mapping controller names ('HandIK.L', 'HandIK.R', 'ElbowPole.L', 'ElbowPole.R')
        to their Empty objects.
    """
    valid_influence = _validate_influence(initial_influence, param_name="initial_influence")
    arm = _resolve_armature(armature_obj)

    # [INTRODUCED 2026-11-12T00:01:12+08:00]
    # FUNCTION: setup_arm_ik
    # PURPOSE: Enforce existing cleanup and FAILED isolation gates before controller ownership object enumeration
    # REASON: Task 10-B fix-3, TEST-163
    for rec in managed_armature_identities.values():
        if rec.original_blender_ref is arm:
            if (
                rec.isolation_state != armature_isolation_state.NONE
                or rec.registry_session_id in isolated_failed_armatures
            ):
                assert_arm_rig_cleanup_gate(arm, rec)
                assert_arm_rig_failed_isolation_gate(arm, rec)
            break

    # Full role ownership admission, including same-name external EMPTY
    # objects. This runs before creating collections or modifying controllers.
    require_existing_arm_ik_controller_ownership(arm, scope='setup_arm_ik')

    # Preflight check 4 controller names for external wrong-type conflicts before entering transaction (F14-05 Entrance A)
    active_tx = active_transaction_stack[-1] if active_transaction_stack else None
    for c_name in (
        arm_ik_target_names["L"],
        arm_ik_target_names["R"],
        arm_pole_target_names["L"],
        arm_pole_target_names["R"],
    ):
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is not None and c_obj.type != "EMPTY":
            if not verify_transaction_wrong_type_object_ownership(c_obj, active_tx, arm):
                raise ExternalControllerNameConflictError(
                    f"EXTERNAL_CONTROLLER_NAME_CONFLICT: Controller '{c_name}' matches pre-existing or external "
                    f"non-EMPTY object '{c_obj.name}' (type='{c_obj.type}') not owned by active transaction."
                )

    with arm_rig_transaction(arm):
        root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
        collection = ensure_character_collection()

        controls: Dict[str, bpy.types.Object] = {}

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_name = arm_ik_target_names[side]
            pole_name = arm_pole_target_names[side]

            ik_obj, ik_is_new = get_or_create_empty(
                name=ik_name,
                display_type="CUBE",
                display_size=0.04,
                parent=root_obj,
                collection=collection,
            )
            if ik_is_new and side == "L":
                trigger_fault_injection("setup_arm_ik_after_first_controller", {"ik_obj": ik_obj})
                trigger_fault_injection("set_hand_ik_target_during_auto_init", {"ik_obj": ik_obj})

            pole_obj, pole_is_new = get_or_create_empty(
                name=pole_name,
                display_type="SPHERE",
                display_size=0.035,
                parent=root_obj,
                collection=collection,
            )

            # Set neutral rest positions only for newly created controllers
            if ik_is_new:
                ik_obj.location = Vector((sign * shoulder_x_offset, 0.0, wrist_rest_z))
                ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

            if pole_is_new:
                pole_obj.location = Vector((
                    sign * (shoulder_x_offset + default_pole_outward_offset),
                    -default_pole_backward_offset,
                    elbow_rest_z,
                ))
                pole_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

            controls[ik_name] = ik_obj
            controls[pole_name] = pole_obj

            p_up = arm.pose.bones[f"upper_arm.{side}"]
            p_fore = arm.pose.bones[f"forearm.{side}"]
            p_hand = arm.pose.bones[f"hand.{side}"]

            # Shoulder ball joint: unconstrained 3D rotation during IK
            p_up.lock_ik_x = False
            p_up.lock_ik_y = False
            p_up.lock_ik_z = False

            # Elbow hinge joint: flex on sagittal local X (positive is forward flexion)
            # Lock Y (axial twist) and Z (lateral adduction/abduction)
            p_fore.lock_ik_x = False
            p_fore.lock_ik_y = True
            p_fore.lock_ik_z = True
            p_fore.use_ik_limit_x = True
            p_fore.ik_min_x = math.radians(0.0)      # Fully extended (straight)
            p_fore.ik_max_x = math.radians(150.0)    # Maximum anatomical elbow flexion

            # Resolve or configure existing ArmIK constraint
            ik_con = None
            con_name_ik = arm_ik_constraint_names[side]
            for idx, con in enumerate(list(p_fore.constraints)):
                if con.name == con_name_ik:
                    if con.type == "IK":
                        ik_con = con
                    else:
                        if active_transaction_stack:
                            tx = active_transaction_stack[-1]
                            orig_name = con.name
                            orig_mute = con.mute
                            orig_idx = idx
                            stashed_name = f"__stashed_con_{orig_name}_{uuid4().hex[:6]}"
                            con.name = stashed_name
                            con.mute = True
                            tx.stashed_constraints.append({
                                "pbone": p_fore,
                                "con": con,
                                "con_ptr": con.as_pointer(),
                                "orig_name": orig_name,
                                "orig_mute": orig_mute,
                                "orig_idx": orig_idx,
                            })
                        else:
                            raise RuntimeError("Cannot stash or remove wrong-type constraint without active transaction")
                elif con.type == "IK" and con.name.startswith("ArmIK"):
                    if active_transaction_stack:
                        tx = active_transaction_stack[-1]
                        orig_name = con.name
                        orig_mute = con.mute
                        orig_idx = idx
                        stashed_name = f"__stashed_con_{orig_name}_{uuid4().hex[:6]}"
                        con.name = stashed_name
                        con.mute = True
                        tx.stashed_constraints.append({
                            "pbone": p_fore,
                            "con": con,
                            "con_ptr": con.as_pointer(),
                            "orig_name": orig_name,
                            "orig_mute": orig_mute,
                            "orig_idx": orig_idx,
                        })
                    else:
                        raise RuntimeError("Cannot stash or remove wrong-type constraint without active transaction")

            newly_created_ik_con = False
            tx = active_transaction_stack[-1] if active_transaction_stack else None
            if ik_con is None:
                ik_con = authorized_create_constraint(
                    pbone=p_fore,
                    con_type="IK",
                    con_name=con_name_ik,
                    active_tx=tx,
                    arm=arm,
                )
                ik_con.influence = valid_influence
                newly_created_ik_con = True

            authorized_assign_constraint_targets(
                pbone=p_fore,
                con=ik_con,
                target=ik_obj,
                pole_target=pole_obj,
                active_tx=tx,
            )
            ik_con.chain_count = 2
            ik_con.use_tail = True
            ik_con.use_stretch = False
            ik_con.pole_angle = math.radians(-90.0)

            # Resolve or configure existing HandRotation constraint
            rot_con = None
            con_name_rot = hand_rot_constraint_names[side]
            for idx, con in enumerate(list(p_hand.constraints)):
                if con.name == con_name_rot:
                    if con.type == "COPY_ROTATION":
                        rot_con = con
                    else:
                        if active_transaction_stack:
                            tx = active_transaction_stack[-1]
                            orig_name = con.name
                            orig_mute = con.mute
                            orig_idx = idx
                            stashed_name = f"__stashed_con_{orig_name}_{uuid4().hex[:6]}"
                            con.name = stashed_name
                            con.mute = True
                            tx.stashed_constraints.append({
                                "pbone": p_hand,
                                "con": con,
                                "con_ptr": con.as_pointer(),
                                "orig_name": orig_name,
                                "orig_mute": orig_mute,
                                "orig_idx": orig_idx,
                            })
                        else:
                            raise RuntimeError("Cannot stash or remove wrong-type constraint without active transaction")
                elif con.type == "COPY_ROTATION" and con.name.startswith("HandRotation"):
                    if active_transaction_stack:
                        tx = active_transaction_stack[-1]
                        orig_name = con.name
                        orig_mute = con.mute
                        orig_idx = idx
                        stashed_name = f"__stashed_con_{orig_name}_{uuid4().hex[:6]}"
                        con.name = stashed_name
                        con.mute = True
                        tx.stashed_constraints.append({
                            "pbone": p_hand,
                            "con": con,
                            "con_ptr": con.as_pointer(),
                            "orig_name": orig_name,
                            "orig_mute": orig_mute,
                            "orig_idx": orig_idx,
                        })
                    else:
                        raise RuntimeError("Cannot stash or remove wrong-type constraint without active transaction")

            if rot_con is None:
                rot_con = authorized_create_constraint(
                    pbone=p_hand,
                    con_type="COPY_ROTATION",
                    con_name=con_name_rot,
                    active_tx=tx,
                    arm=arm,
                )
                rot_con.influence = valid_influence

            authorized_assign_constraint_targets(
                pbone=p_hand,
                con=rot_con,
                target=ik_obj,
                active_tx=tx,
            )
            rot_con.target_space = "WORLD"
            rot_con.owner_space = "WORLD"
            rot_con.mix_mode = "REPLACE"

            # Apply pre-bend hint only when establishing an IK chain for the first time
            if newly_created_ik_con:
                _apply_arm_ik_prebend_hint_side(arm, side)

            trigger_fault_injection("setup_arm_ik_after_constraints_or_prebend", {"side": side, "arm": arm})

        depsgraph_update()
        return controls
