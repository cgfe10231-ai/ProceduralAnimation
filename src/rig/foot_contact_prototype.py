"""Task 4D runner: build and verify procedural support-foot locking and flat-ground (Z=0)
contact control, measure bone & mesh world drift under small and out-of-reach root
displacements, and save isolated `output/character_foot_contact_prototype.blend`
and `output/preview_character_foot_contact.png`.

Does not overwrite Task 3, Task 4A, Task 4B, or Task 4C artifacts.
Does not implement full walk cycles, step planning, or root motion animation.
"""

import os
import sys

import bpy
from mathutils import Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.render import configure_render
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.foot_contact import (
    evaluate_foot_support,
    get_foot_support_state,
    lock_foot_contact,
    move_character_root_with_support,
    unlock_foot_contact,
)
from src.rig.ik import (
    HIP_X_OFFSET,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose, set_bone_rotation


def _ensure_scene_with_ik_rig(config: PipelineConfig) -> bpy.types.Object:
    """Load existing Task 4C / 4B / 4A / 3 scene and initialize clean character + 19-bone IK rig."""
    for candidate in (
        config.character_ik_blend_path,
        config.character_rig_blend_path,
        config.character_blend_path,
        config.blend_file_path,
    ):
        if os.path.isfile(candidate):
            print(f"[TASK4D] Opening existing scene: {candidate}")
            bpy.ops.wm.open_mainfile(filepath=candidate)
            break
    else:
        from src.camera import setup_camera
        from src.lighting import setup_lighting
        from src.scene import setup_scene

        setup_scene(config)
        setup_lighting(config)
        setup_camera(config)
        configure_render(config)

    build_character(config)
    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = build_rig(config, character_root=root_obj)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    reset_leg_ik(arm_obj)
    return arm_obj


def run_foot_contact_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 68)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 4D FOOT CONTACT & LOCK PROTOTYPE")
    print("=" * 68)

    arm_obj = _ensure_scene_with_ik_rig(config)
    root_obj = bpy.data.objects["CharacterRoot"]
    start_x, start_y, start_z = config.character_path_points[0]

    # -------------------------------------------------------------------------
    # Test 1: Lock Left Foot at start waypoint, verify lock protection & free Right Foot
    # -------------------------------------------------------------------------
    reset_leg_ik(arm_obj)
    root_obj.location = Vector((start_x, start_y, start_z))
    bpy.context.view_layer.update()

    lock_l_init = lock_foot_contact(
        arm_obj,
        "L",
        contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0),
        target_rotation_deg=(0.0, 0.0, 0.0),
    )
    state_r_free = get_foot_support_state(arm_obj, "R")
    if not lock_l_init["is_locked"] or state_r_free["is_locked"]:
        raise RuntimeError("Independent lock state initialization failed")

    # Verify locked foot rejects direct set_foot_ik_target
    guard_triggered = False
    try:
        set_foot_ik_target(arm_obj, "L", (start_x - HIP_X_OFFSET, start_y + 0.2, 0.25))
    except RuntimeError:
        guard_triggered = True
    if not guard_triggered:
        raise RuntimeError("Locked foot L failed to reject direct set_foot_ik_target call")

    # -------------------------------------------------------------------------
    # Test 2A: Pure horizontal root shift (+0.03m X, +0.08m Y, 0.0m Z) with Left Foot locked
    # -------------------------------------------------------------------------
    states_horiz = move_character_root_with_support(
        arm_obj, (start_x + 0.03, start_y + 0.08, start_z)
    )
    # Unlocked right foot can still be freely posed via IK while left foot stays locked
    swing_r = set_foot_ik_target(
        arm_obj, "R", (start_x + HIP_X_OFFSET + 0.03, start_y + 0.24, start_z + 0.25)
    )
    support_l_horiz = evaluate_foot_support(arm_obj, "L")
    print(
        f"[TASK4D] Test 2A (Pure Horizontal Root Shift +0.03X, +0.08Y, 0.00Z | Left Locked):\n"
        f"  status={support_l_horiz['reach_status']}, is_reachable={support_l_horiz['is_reachable']}, "
        f"hip_dist={support_l_horiz['hip_to_target_dist']:.5f}m\n"
        f"  controller_drift={support_l_horiz['controller_drift']:.6f}m, "
        f"ankle_bone_drift={support_l_horiz['ankle_bone_drift']:.6f}m (horiz={support_l_horiz['ankle_horiz_drift']:.6f}m), "
        f"toe_bone_drift={support_l_horiz['toe_bone_drift']:.6f}m, "
        f"mesh_center_drift={support_l_horiz['mesh_center_drift']:.6f}m, "
        f"Foot_L minZ={support_l_horiz['foot_min_z']:.6f}m\n"
        f"  Unlocked Right Foot IK target error={swing_r['target_error']:.6f}m, Foot_R minZ={swing_r['foot_min_z']:.4f}m"
    )
    if not support_l_horiz["is_locked"] or not support_l_horiz["is_reachable"]:
        raise RuntimeError("Left foot should be locked and reachable under small horizontal shift")
    if support_l_horiz["controller_drift"] > 1e-6:
        raise RuntimeError(f"Locked controller drifted: {support_l_horiz['controller_drift']}")
    if support_l_horiz["ankle_bone_drift"] > 0.010 or support_l_horiz["mesh_center_drift"] > 0.010:
        raise RuntimeError(f"Support foot drift exceeded 10mm: {support_l_horiz['ankle_bone_drift']}")
    if support_l_horiz["foot_min_z"] < -1e-3 or support_l_horiz["foot_min_z"] > 0.010:
        raise RuntimeError(f"Support foot sole left ground vicinity: minZ={support_l_horiz['foot_min_z']}")
    if swing_r["target_error"] > 0.005:
        raise RuntimeError(f"Unlocked right foot failed to reach IK target: {swing_r['target_error']}")

    # -------------------------------------------------------------------------
    # Test 2B: Horizontal root shift (+0.02m X, +0.10m Y) with slight natural crouch (-0.015m Z)
    # -------------------------------------------------------------------------
    move_character_root_with_support(
        arm_obj, (start_x + 0.02, start_y + 0.10, start_z - 0.015)
    )
    support_l_strict = evaluate_foot_support(arm_obj, "L")
    print(
        f"[TASK4D] Test 2B (Root Shift +0.02X, +0.10Y, -0.015Z | Strict Reach):\n"
        f"  status={support_l_strict['reach_status']}, strictly_in_reach={support_l_strict['strictly_in_reach']}, "
        f"hip_dist={support_l_strict['hip_to_target_dist']:.5f}m (max={support_l_strict['max_leg_reach']:.2f}m)\n"
        f"  controller_drift={support_l_strict['controller_drift']:.6f}m, "
        f"ankle_bone_drift={support_l_strict['ankle_bone_drift']:.6f}m, "
        f"toe_bone_drift={support_l_strict['toe_bone_drift']:.6f}m, "
        f"mesh_center_drift={support_l_strict['mesh_center_drift']:.6f}m, "
        f"Foot_L minZ={support_l_strict['foot_min_z']:.6f}m"
    )
    if not support_l_strict["strictly_in_reach"] or support_l_strict["ankle_bone_drift"] > 0.001:
        raise RuntimeError(f"Expected sub-millimeter drift inside strict reach, got {support_l_strict['ankle_bone_drift']}")

    # -------------------------------------------------------------------------
    # Test 2C: Swap Support — Unlock Left, Lock Right, Shift Root, Lift Left
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L")
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)
    lock_foot_contact(
        arm_obj,
        "R",
        contact_world_xyz=(start_x + HIP_X_OFFSET, start_y, 0.0),
        target_rotation_deg=(0.0, 0.0, 0.0),
    )
    move_character_root_with_support(
        arm_obj, (start_x - 0.02, start_y + 0.10, start_z - 0.015)
    )
    swing_l = set_foot_ik_target(
        arm_obj, "L", (start_x - HIP_X_OFFSET - 0.02, start_y + 0.24, start_z + 0.25)
    )
    support_r = evaluate_foot_support(arm_obj, "R")
    print(
        f"[TASK4D] Test 2C (Right Foot Locked, Left Foot Lifted):\n"
        f"  R status={support_r['reach_status']}, R ankle_bone_drift={support_r['ankle_bone_drift']:.6f}m, "
        f"R mesh_center_drift={support_r['mesh_center_drift']:.6f}m, Foot_R minZ={support_r['foot_min_z']:.6f}m\n"
        f"  Unlocked Left Foot IK target error={swing_l['target_error']:.6f}m, Foot_L minZ={swing_l['foot_min_z']:.4f}m"
    )
    if not support_r["is_locked"] or not support_r["is_reachable"] or support_r["ankle_bone_drift"] > 0.001:
        raise RuntimeError("Right foot support lock failed")

    # -------------------------------------------------------------------------
    # Test 3: Boundary & Out-of-Reach Root Movement (Verify NO secret target move & explicit unreachable return)
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "R")
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)
    lock_foot_contact(
        arm_obj,
        "L",
        contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0),
        target_rotation_deg=(0.0, 0.0, 0.0),
    )

    # 3A: At horizontal support boundary (d_y = +0.15m at Z = 0.0, hip_dist = 0.8336m <= 0.8350m)
    move_character_root_with_support(arm_obj, (start_x, start_y + 0.15, start_z))
    boundary_l = evaluate_foot_support(arm_obj, "L")
    print(
        f"[TASK4D] Test 3A (At Reach Boundary +0.15m Y): "
        f"status={boundary_l['reach_status']}, is_reachable={boundary_l['is_reachable']}, "
        f"hip_dist={boundary_l['hip_to_target_dist']:.5f}m, ankle_bone_drift={boundary_l['ankle_bone_drift']:.5f}m"
    )
    if not boundary_l["is_reachable"]:
        raise RuntimeError("Boundary case (+0.15m Y) should still be within effective support reach")

    # 3B: Exceeding reach boundary (d_y = +0.45m at Z = 0.0, hip_dist = 0.9354m >> 0.82m)
    move_character_root_with_support(arm_obj, (start_x, start_y + 0.45, start_z))
    exceed_l = evaluate_foot_support(arm_obj, "L")
    print(
        f"[TASK4D] Test 3B (Exceeding Reach Boundary +0.45m Y):\n"
        f"  status={exceed_l['reach_status']}, is_reachable={exceed_l['is_reachable']}, "
        f"hip_dist={exceed_l['hip_to_target_dist']:.5f}m (max={exceed_l['max_leg_reach']:.2f}m)\n"
        f"  locked_contact={tuple(round(v, 4) for v in exceed_l['contact_world'])}, "
        f"controller_world={tuple(round(v, 4) for v in exceed_l['controller_world'])}, "
        f"controller_drift={exceed_l['controller_drift']:.6f}m\n"
        f"  actual_ankle_bone_drift={exceed_l['ankle_bone_drift']:.5f}m, "
        f"actual_mesh_center_drift={exceed_l['mesh_center_drift']:.5f}m"
    )
    if exceed_l["is_reachable"] or exceed_l["reach_status"] != "UNREACHABLE":
        raise RuntimeError("Exceeding reach boundary failed to report UNREACHABLE")
    if exceed_l["controller_drift"] > 1e-6:
        raise RuntimeError("Locked point was secretly moved when root exceeded reach!")

    # -------------------------------------------------------------------------
    # Test 4: Release Support Lock and verify normal IK target control is restored
    # -------------------------------------------------------------------------
    released_l = unlock_foot_contact(arm_obj, "L")
    if released_l["is_locked"]:
        raise RuntimeError("unlock_foot_contact failed to clear is_locked")
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)
    free_test_l = set_foot_ik_target(arm_obj, "L", (start_x - HIP_X_OFFSET, start_y + 0.16, start_z + 0.22))
    if free_test_l["target_error"] > 0.005:
        raise RuntimeError("Released foot L failed to accept normal IK target after unlock")

    # -------------------------------------------------------------------------
    # Final Showcase Pose for Saved .blend and Preview Image:
    # Left foot locked on the start waypoint disc (-0.11, -8.0, 0.0),
    # CharacterRoot shifted forward (+0.10m Y, +0.02m X, -0.015m Z),
    # Right foot unlocked and lifted forward in a mid-step pose (0.13, -7.68, 0.25).
    # -------------------------------------------------------------------------
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)
    lock_foot_contact(
        arm_obj,
        "L",
        contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0),
        target_rotation_deg=(0.0, 0.0, 0.0),
    )
    move_character_root_with_support(
        arm_obj, (start_x + 0.02, start_y + 0.10, start_z - 0.015)
    )
    showcase_r = set_foot_ik_target(
        arm_obj,
        "R",
        (start_x + HIP_X_OFFSET + 0.02, start_y + 0.32, start_z + 0.24),
        foot_rotation_deg=(8.0, 0.0, 0.0),
    )
    showcase_l = evaluate_foot_support(arm_obj, "L")

    set_bone_rotation(arm_obj, "upper_arm.L", (24.0, 0.0, -8.0), update=False)
    set_bone_rotation(arm_obj, "forearm.L", (22.0, 0.0, 0.0), update=False)
    set_bone_rotation(arm_obj, "upper_arm.R", (-20.0, 0.0, 8.0), update=False)
    set_bone_rotation(arm_obj, "forearm.R", (18.0, 0.0, 0.0), update=True)

    configure_render(config)
    scene = bpy.context.scene
    scene.frame_set(config.frame_start)

    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        cam_obj.location = (start_x + 1.95, start_y + 4.35, 1.25)
        target_obj.location = (start_x, start_y + 0.10, 0.88)
        cam_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        target_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        bpy.context.view_layer.update()

    preview_path = config.character_foot_contact_preview_path
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    print(f"[TASK4D] Foot contact preview written: {preview_path}")

    blend_path = config.character_foot_contact_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK4D] Foot contact prototype blend written: {blend_path}")
    print("[TASK4D] COMPLETED SUCCESSFULLY")
    print("=" * 68)

    return {
        "horiz_shift_ankle_drift": round(support_l_horiz["ankle_bone_drift"], 6),
        "horiz_shift_mesh_drift": round(support_l_horiz["mesh_center_drift"], 6),
        "strict_shift_ankle_drift": round(support_l_strict["ankle_bone_drift"], 6),
        "strict_shift_mesh_drift": round(support_l_strict["mesh_center_drift"], 6),
        "exceed_reachable": exceed_l["is_reachable"],
        "exceed_controller_drift": round(exceed_l["controller_drift"], 6),
        "exceed_ankle_drift": round(exceed_l["ankle_bone_drift"], 6),
        "showcase_l_drift": round(showcase_l["ankle_bone_drift"], 6),
        "blend_path": blend_path,
        "preview_path": preview_path,
    }


if __name__ == "__main__":
    try:
        run_foot_contact_prototype()
    except Exception as e:
        print(f"[TASK4D_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
