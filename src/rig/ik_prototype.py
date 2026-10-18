"""Task 4C runner: build procedural two-bone leg IK on the 19-bone CharacterArmature,
verify neutral stance, left-foot lift, right-foot lift, out-of-reach target clamping,
and ground-penetration protection, and save isolated `output/character_ik_prototype.blend`
and `output/preview_character_ik_pose.png`.

Does not overwrite Task 3, Task 4A, or Task 4B artifacts.
Does not implement walk cycles, motion transitions, or root motion animation.
"""

import os
import sys

import bpy

from src.character.builder import REQUIRED_PARTS, build_character, world_min_z
from src.config import PipelineConfig
from src.render import configure_render
from src.rig.builder import BONE_HIERARCHY, PART_TO_BONE_MAP, bind_character_to_rig, build_rig
from src.rig.ik import (
    ANKLE_REST_Z,
    FOOT_ROT_CONSTRAINT_NAMES,
    HIP_X_OFFSET,
    IK_CONSTRAINT_NAMES,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    POLE_TARGET_NAMES,
    get_leg_ik_state,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import get_part_world_center, reset_pose, set_bone_rotation


def _ensure_scene_with_rigged_character(config: PipelineConfig) -> bpy.types.Object:
    """Load existing Task 4B / 4A / 3 scene and ensure the 19-bone rigged character exists."""
    task4b_blend = config.character_rig_blend_path
    task4a_blend = config.character_blend_path
    task3_blend = config.blend_file_path

    if os.path.isfile(task4b_blend):
        print(f"[TASK4C] Opening existing Task 4B scene: {task4b_blend}")
        bpy.ops.wm.open_mainfile(filepath=task4b_blend)
    elif os.path.isfile(task4a_blend):
        print(f"[TASK4C] Opening existing Task 4A scene: {task4a_blend}")
        bpy.ops.wm.open_mainfile(filepath=task4a_blend)
    elif os.path.isfile(task3_blend):
        print(f"[TASK4C] Opening existing Task 3 scene: {task3_blend}")
        bpy.ops.wm.open_mainfile(filepath=task3_blend)
    else:
        from src.camera import setup_camera
        from src.lighting import setup_lighting
        from src.scene import setup_scene

        setup_scene(config)
        setup_lighting(config)
        setup_camera(config)
        configure_render(config)

    # Rebuild clean character + 19-bone rig from neutral rest state
    build_character(config)
    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = build_rig(config, character_root=root_obj)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    return arm_obj


def run_ik_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 64)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 4C TWO-BONE LEG IK PROTOTYPE")
    print("=" * 64)

    arm_obj = _ensure_scene_with_rigged_character(config)
    setup_leg_ik(arm_obj)

    start_x, start_y, start_z = config.character_path_points[0]

    # 1. Verify IK constraints, pole targets, chain length = 2, and 13-part bindings
    for side in ("L", "R"):
        p_shin = arm_obj.pose.bones[f"shin.{side}"]
        ik_con = p_shin.constraints.get(IK_CONSTRAINT_NAMES[side])
        if ik_con is None or ik_con.type != "IK":
            raise RuntimeError(f"Missing IK constraint on shin.{side}")
        if ik_con.chain_count != 2:
            raise RuntimeError(f"Expected chain_count=2 on shin.{side}, got {ik_con.chain_count}")
        if ik_con.target != bpy.data.objects.get(IK_TARGET_NAMES[side]):
            raise RuntimeError(f"Invalid IK target on shin.{side}")
        if ik_con.pole_target != bpy.data.objects.get(POLE_TARGET_NAMES[side]):
            raise RuntimeError(f"Invalid Pole target on shin.{side}")

        p_foot = arm_obj.pose.bones[f"foot.{side}"]
        rot_con = p_foot.constraints.get(FOOT_ROT_CONSTRAINT_NAMES[side])
        if rot_con is None or rot_con.type != "COPY_ROTATION":
            raise RuntimeError(f"Missing foot orientation constraint on foot.{side}")

    for part_name, expected_bone in PART_TO_BONE_MAP.items():
        part_obj = bpy.data.objects.get(part_name)
        if part_obj is None or part_obj.parent != arm_obj or part_obj.parent_bone != expected_bone:
            raise RuntimeError(f"Part '{part_name}' binding broken")

    # 2. Pose 1: Neutral Standing Pose
    reset_leg_ik(arm_obj)
    neutral_l = get_leg_ik_state(arm_obj, "L")
    neutral_r = get_leg_ik_state(arm_obj, "R")
    neutral_centers = {name: get_part_world_center(name) for name in REQUIRED_PARTS}
    print(
        f"[TASK4C] Pose 1 (Neutral): "
        f"L err={neutral_l['target_error']:.5f}m, Foot_L minZ={neutral_l['foot_min_z']:.6f}m | "
        f"R err={neutral_r['target_error']:.5f}m, Foot_R minZ={neutral_r['foot_min_z']:.6f}m"
    )
    if neutral_l["target_error"] > 0.01 or neutral_r["target_error"] > 0.01:
        raise RuntimeError(f"Neutral IK target error too large: L={neutral_l['target_error']}, R={neutral_r['target_error']}")
    if abs(neutral_l["foot_min_z"]) > 1e-3 or abs(neutral_r["foot_min_z"]) > 1e-3:
        raise RuntimeError(
            f"Neutral stance feet not grounded at Z=0: L={neutral_l['foot_min_z']:.6f}, R={neutral_r['foot_min_z']:.6f}"
        )

    # 3. Pose 2: Left Foot Lifted (forward +0.18m, up to Z=0.28m)
    reset_leg_ik(arm_obj)
    lift_l_target = (start_x - HIP_X_OFFSET, start_y + 0.18, start_z + 0.28)
    state_lift_l = set_foot_ik_target(arm_obj, "L", lift_l_target)
    state_stay_r = get_leg_ik_state(arm_obj, "R")
    r_thigh_disp = (get_part_world_center("UpperLeg_R") - neutral_centers["UpperLeg_R"]).length
    r_shin_disp = (get_part_world_center("LowerLeg_R") - neutral_centers["LowerLeg_R"]).length
    r_foot_disp = (get_part_world_center("Foot_R") - neutral_centers["Foot_R"]).length
    print(
        f"[TASK4C] Pose 2 (Left Lift): "
        f"L err={state_lift_l['target_error']:.5f}m, knee_flex={state_lift_l['knee_flexion_deg']:.2f}deg, "
        f"knee_fwd_y={state_lift_l['knee_forward_y']:+.4f}m, Foot_L minZ={state_lift_l['foot_min_z']:.4f}m | "
        f"Right leg max disp={max(r_thigh_disp, r_shin_disp, r_foot_disp):.6f}m, Foot_R minZ={state_stay_r['foot_min_z']:.6f}m"
    )
    if state_lift_l["target_error"] > 0.01:
        raise RuntimeError(f"Left lift target error too high: {state_lift_l['target_error']:.5f}m")
    if state_lift_l["knee_forward_y"] <= 0.05:
        raise RuntimeError(f"Left knee did not bend forward (+Y): knee_forward_y={state_lift_l['knee_forward_y']:.4f}m")
    if max(r_thigh_disp, r_shin_disp, r_foot_disp) > 1e-4:
        raise RuntimeError("Right leg moved unexpectedly when moving Left foot IK target")
    if abs(state_stay_r["foot_min_z"]) > 1e-3:
        raise RuntimeError(f"Planted Foot_R penetrated or lifted: minZ={state_stay_r['foot_min_z']:.6f}m")

    # 4. Pose 3: Right Foot Lifted (forward +0.18m, up to Z=0.28m)
    reset_leg_ik(arm_obj)
    lift_r_target = (start_x + HIP_X_OFFSET, start_y + 0.18, start_z + 0.28)
    state_lift_r = set_foot_ik_target(arm_obj, "R", lift_r_target)
    state_stay_l = get_leg_ik_state(arm_obj, "L")
    l_thigh_disp = (get_part_world_center("UpperLeg_L") - neutral_centers["UpperLeg_L"]).length
    l_shin_disp = (get_part_world_center("LowerLeg_L") - neutral_centers["LowerLeg_L"]).length
    l_foot_disp = (get_part_world_center("Foot_L") - neutral_centers["Foot_L"]).length
    print(
        f"[TASK4C] Pose 3 (Right Lift): "
        f"R err={state_lift_r['target_error']:.5f}m, knee_flex={state_lift_r['knee_flexion_deg']:.2f}deg, "
        f"knee_fwd_y={state_lift_r['knee_forward_y']:+.4f}m, Foot_R minZ={state_lift_r['foot_min_z']:.4f}m | "
        f"Left leg max disp={max(l_thigh_disp, l_shin_disp, l_foot_disp):.6f}m, Foot_L minZ={state_stay_l['foot_min_z']:.6f}m"
    )
    if state_lift_r["target_error"] > 0.01:
        raise RuntimeError(f"Right lift target error too high: {state_lift_r['target_error']:.5f}m")
    if state_lift_r["knee_forward_y"] <= 0.05:
        raise RuntimeError(f"Right knee did not bend forward (+Y): knee_forward_y={state_lift_r['knee_forward_y']:.4f}m")
    if max(l_thigh_disp, l_shin_disp, l_foot_disp) > 1e-4:
        raise RuntimeError("Left leg moved unexpectedly when moving Right foot IK target")
    if abs(state_stay_l["foot_min_z"]) > 1e-3:
        raise RuntimeError(f"Planted Foot_L penetrated or lifted: minZ={state_stay_l['foot_min_z']:.6f}m")

    # 5. Test 4: Out-of-reach & Sub-ground target clamping
    reset_leg_ik(arm_obj)
    extreme_target = (start_x - HIP_X_OFFSET, start_y + 2.0, start_z - 0.50)
    clamped_state = set_foot_ik_target(arm_obj, "L", extreme_target, clamp_reach=True, clamp_ground=True)
    hip_dist = (clamped_state["applied_world"] - clamped_state["hip_world"]).length
    print(
        f"[TASK4C] Pose 4 (Out-of-reach & Sub-ground clamp): "
        f"requested={tuple(round(v, 3) for v in extreme_target)} -> "
        f"applied={tuple(round(v, 4) for v in clamped_state['applied_world'])}, "
        f"hip_dist={hip_dist:.4f}m (max={MAX_LEG_REACH:.2f}m), "
        f"clamped_reach={clamped_state['clamped_reach']}, clamped_ground={clamped_state['clamped_ground']}, "
        f"target_err={clamped_state['target_error']:.5f}m, Foot_L minZ={clamped_state['foot_min_z']:.6f}m"
    )
    if not clamped_state["clamped_reach"] or not clamped_state["clamped_ground"]:
        raise RuntimeError("Out-of-reach/sub-ground target was not flagged as clamped")
    if hip_dist > MAX_LEG_REACH + 1e-4:
        raise RuntimeError(f"Clamped target distance {hip_dist:.4f}m exceeds MAX_LEG_REACH {MAX_LEG_REACH}m")
    if clamped_state["foot_min_z"] < -1e-3:
        raise RuntimeError(f"Clamped target penetrated ground: Foot_L minZ={clamped_state['foot_min_z']:.6f}m")

    # 6. Set final showcase IK pose for saved .blend and preview image:
    # Left leg raised in clear stepping/marching knee-lift pose, right foot planted on Z=0,
    # with subtle upper-body counter-arm pose for visual clarity.
    reset_leg_ik(arm_obj)
    showcase_l = set_foot_ik_target(
        arm_obj,
        "L",
        (start_x - HIP_X_OFFSET, start_y + 0.18, start_z + 0.28),
        foot_rotation_deg=(0.0, 0.0, 0.0),
    )
    showcase_r = set_foot_ik_target(
        arm_obj,
        "R",
        (start_x + HIP_X_OFFSET, start_y, start_z + ANKLE_REST_Z),
        foot_rotation_deg=(0.0, 0.0, 0.0),
    )
    set_bone_rotation(arm_obj, "upper_arm.L", (-22.0, 0.0, -8.0), update=False)
    set_bone_rotation(arm_obj, "forearm.L", (20.0, 0.0, 0.0), update=False)
    set_bone_rotation(arm_obj, "upper_arm.R", (28.0, 0.0, 8.0), update=False)
    set_bone_rotation(arm_obj, "forearm.R", (25.0, 0.0, 0.0), update=True)

    # Frame camera in the obstacle-free corridor at a 3/4 front-side angle so knee bend & foot level are clearly visible
    configure_render(config)
    scene = bpy.context.scene
    scene.frame_set(config.frame_start)

    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        cam_obj.location = (start_x - 1.95, start_y + 4.35, 1.28)
        target_obj.location = (start_x, start_y + 0.05, 0.90)
        cam_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        target_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        bpy.context.view_layer.update()

    preview_path = config.character_ik_preview_path
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    print(f"[TASK4C] Leg IK preview written: {preview_path}")

    blend_path = config.character_ik_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK4C] Leg IK prototype blend written: {blend_path}")
    print("[TASK4C] COMPLETED SUCCESSFULLY")
    print("=" * 64)

    return {
        "neutral_l_error": round(neutral_l["target_error"], 6),
        "neutral_r_error": round(neutral_r["target_error"], 6),
        "lift_l_error": round(state_lift_l["target_error"], 6),
        "lift_l_knee_flex_deg": round(state_lift_l["knee_flexion_deg"], 2),
        "lift_r_error": round(state_lift_r["target_error"], 6),
        "lift_r_knee_flex_deg": round(state_lift_r["knee_flexion_deg"], 2),
        "clamped_hip_dist": round(hip_dist, 4),
        "blend_path": blend_path,
        "preview_path": preview_path,
    }


if __name__ == "__main__":
    try:
        run_ik_prototype()
    except Exception as e:
        print(f"[TASK4C_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
