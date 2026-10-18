"""Task 4B runner: build procedural humanoid Armature, bind the 13 body parts,
verify rest-pose grounding and multi-joint pose response, and save isolated
`output/character_rig_prototype.blend` and `output/preview_character_rig_pose.png`.

Does not overwrite Task 3 (`procedural_scene.blend`) or Task 4A (`character_prototype.blend`).
Does not implement IK, walk cycles, or keyframed root motion.
"""

import os
import sys
from typing import Dict, Tuple

import bpy
from mathutils import Vector

from src.config import PipelineConfig
from src.character.builder import REQUIRED_PARTS, build_character, world_min_z
from src.rig.builder import BONE_HIERARCHY, PART_TO_BONE_MAP, bind_character_to_rig, build_rig
from src.rig.pose import apply_pose_dict, get_part_world_center, reset_pose
from src.render import configure_render

# Sample static pose modifying 6 joints across arms, leg, and head for verification
SAMPLE_VERIFICATION_POSE_DEG: Dict[str, Tuple[float, float, float]] = {
    "upper_arm.L": (45.0, 0.0, -12.0),   # Left upper arm swung forward and slightly out
    "forearm.L": (40.0, 0.0, 0.0),       # Left elbow bent forward
    "upper_arm.R": (-30.0, 0.0, 12.0),   # Right upper arm swung back and slightly out
    "forearm.R": (25.0, 0.0, 0.0),       # Right elbow slightly bent
    "thigh.L": (28.0, 0.0, 0.0),         # Left thigh lifted forward
    "shin.L": (-35.0, 0.0, 0.0),         # Left knee bent back
    "head": (-10.0, 18.0, 0.0),          # Head slightly raised and turned
}


def _ensure_scene_with_character(config: PipelineConfig):
    """Load existing Task 4A or Task 3 scene and ensure the 13-part character exists."""
    task4a_blend = config.character_blend_path
    task3_blend = config.blend_file_path

    if os.path.isfile(task4a_blend):
        print(f"[TASK4B] Opening existing Task 4A scene: {task4a_blend}")
        bpy.ops.wm.open_mainfile(filepath=task4a_blend)
    elif os.path.isfile(task3_blend):
        print(f"[TASK4B] Opening existing Task 3 scene: {task3_blend}")
        bpy.ops.wm.open_mainfile(filepath=task3_blend)
    else:
        from src.scene import setup_scene
        from src.camera import setup_camera
        from src.lighting import setup_lighting

        setup_scene(config)
        setup_lighting(config)
        setup_camera(config)
        configure_render(config)

    # Ensure all 13 character parts exist in neutral rest state before rigging
    build_character(config)


def run_rig_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 60)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 4B HUMANOID RIG & BINDING")
    print("=" * 60)

    _ensure_scene_with_character(config)

    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = build_rig(config, character_root=root_obj)
    bound_map = bind_character_to_rig(arm_obj)

    # 1. Verify bone hierarchy and count
    for bone_name, expected_parent in BONE_HIERARCHY.items():
        bone = arm_obj.data.bones.get(bone_name)
        if bone is None:
            raise RuntimeError(f"Missing expected bone: {bone_name}")
        actual_parent = bone.parent.name if bone.parent else None
        if actual_parent != expected_parent:
            raise RuntimeError(
                f"Bone '{bone_name}' parent mismatch: expected {expected_parent}, got {actual_parent}"
            )

    # 2. Verify rest-pose grounding and L/R symmetry (no crossover)
    reset_pose(arm_obj)
    start_x, start_y, _ = config.character_path_points[0]
    foot_l_rest_z = world_min_z(bpy.data.objects["Foot_L"])
    foot_r_rest_z = world_min_z(bpy.data.objects["Foot_R"])
    print(f"[TASK4B] Rest pose Foot_L min Z: {foot_l_rest_z:.6f} m")
    print(f"[TASK4B] Rest pose Foot_R min Z: {foot_r_rest_z:.6f} m")
    if abs(foot_l_rest_z) > 1e-4 or abs(foot_r_rest_z) > 1e-4:
        raise RuntimeError(
            f"Rest pose feet not grounded at Z=0: Foot_L={foot_l_rest_z:.6f}, Foot_R={foot_r_rest_z:.6f}"
        )

    for part_name in REQUIRED_PARTS:
        center = get_part_world_center(part_name)
        if part_name.endswith("_L") and not (center.x < start_x - 0.02):
            raise RuntimeError(f"Left part '{part_name}' crossed over or misaligned: X={center.x:.4f}")
        if part_name.endswith("_R") and not (center.x > start_x + 0.02):
            raise RuntimeError(f"Right part '{part_name}' crossed over or misaligned: X={center.x:.4f}")

    rest_centers = {name: get_part_world_center(name) for name in REQUIRED_PARTS}

    # 3. Apply verification pose and assert bound geometry follows bone rotations
    apply_pose_dict(arm_obj, SAMPLE_VERIFICATION_POSE_DEG, reset_first=True)
    posed_centers = {name: get_part_world_center(name) for name in REQUIRED_PARTS}

    moved_parts = {}
    for part_name in ("UpperArm_L", "LowerArm_L", "UpperArm_R", "LowerArm_R", "UpperLeg_L", "LowerLeg_L", "Foot_L"):
        disp = (posed_centers[part_name] - rest_centers[part_name]).length
        moved_parts[part_name] = round(disp, 5)
        print(f"[TASK4B] Pose displacement '{part_name}': {disp:.4f} m")
        if disp < 0.03:
            raise RuntimeError(
                f"Part '{part_name}' did not follow bone rotation (displacement={disp:.5f}m)"
            )

    # Planted right foot must remain grounded at Z=0
    foot_r_posed_z = world_min_z(bpy.data.objects["Foot_R"])
    print(f"[TASK4B] Posed planted Foot_R min Z: {foot_r_posed_z:.6f} m")
    if abs(foot_r_posed_z) > 1e-4:
        raise RuntimeError(f"Support foot Foot_R lifted off ground: min Z={foot_r_posed_z:.6f}")

    # 4. Frame camera in the obstacle-free corridor and render preview
    configure_render(config)
    scene = bpy.context.scene
    scene.frame_set(config.frame_start)

    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        cam_obj.location = (start_x + 1.6, start_y + 4.4, 1.35)
        target_obj.location = (start_x, start_y, 0.88)
        cam_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        target_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        bpy.context.view_layer.update()

    preview_path = config.character_rig_preview_path
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    print(f"[TASK4B] Rig pose preview written: {preview_path}")

    # 5. Save isolated .blend file
    blend_path = config.character_rig_blend_path
    for protected_path in (config.blend_file_path, config.character_blend_path):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK4B] Rig prototype blend written: {blend_path}")
    print("[TASK4B] COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return {
        "bone_count": len(arm_obj.data.bones),
        "bound_parts": len(bound_map),
        "rest_foot_l_z": round(foot_l_rest_z, 6),
        "rest_foot_r_z": round(foot_r_rest_z, 6),
        "moved_parts": moved_parts,
        "blend_path": blend_path,
        "preview_path": preview_path,
    }


if __name__ == "__main__":
    try:
        run_rig_prototype()
    except Exception as e:
        print(f"[TASK4B_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
