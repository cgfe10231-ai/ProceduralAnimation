"""Task 4A runner: add a humanoid placeholder into the existing Task 3 scene.

Saves a separate .blend and a single preview image. Does not overwrite
output/procedural_scene.blend or Task 3 preview_frame_*.png files.
Does not create armatures or animation.
"""

import os
import sys

from src.config import PipelineConfig
from src.character.builder import REQUIRED_PARTS, build_character, world_min_z
from src.render import configure_render


def _ensure_task3_scene(config: PipelineConfig):
    import bpy

    scene_path = config.blend_file_path
    already_loaded = os.path.normcase(os.path.abspath(bpy.data.filepath)) == os.path.normcase(
        os.path.abspath(scene_path)
    )
    if already_loaded and bpy.data.objects.get("GroundPlane") is not None:
        print(f"[TASK4A] Using already-loaded Task 3 scene: {bpy.data.filepath}")
        return

    if os.path.isfile(scene_path):
        print(f"[TASK4A] Opening existing Task 3 scene: {scene_path}")
        bpy.ops.wm.open_mainfile(filepath=scene_path)
        return

    print("[TASK4A] Task 3 .blend missing; rebuilding scene via existing pipeline modules.")
    from src.scene import setup_scene
    from src.camera import setup_camera
    from src.lighting import setup_lighting

    setup_scene(config)
    setup_lighting(config)
    setup_camera(config)
    configure_render(config)


def run_character_prototype(config: PipelineConfig = None) -> dict:
    import bpy

    if config is None:
        config = PipelineConfig()

    print("=" * 60)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 4A CHARACTER PLACEHOLDER")
    print("=" * 60)

    _ensure_task3_scene(config)
    built = build_character(config)

    armature_count = sum(1 for obj in bpy.data.objects if obj.type == "ARMATURE")
    if armature_count:
        raise RuntimeError(f"Task 4A must not create armatures; found {armature_count}")

    start = tuple(config.character_path_points[0])
    root = built["root"]
    root_xy = (round(root.location.x, 6), round(root.location.y, 6))
    start_xy = (round(start[0], 6), round(start[1], 6))
    if root_xy != start_xy:
        raise RuntimeError(f"Character root XY {root_xy} != start waypoint XY {start_xy}")

    missing = [name for name in REQUIRED_PARTS if bpy.data.objects.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing character parts: {missing}")

    bpy.context.view_layer.update()
    foot_min = min(world_min_z(bpy.data.objects["Foot_L"]), world_min_z(bpy.data.objects["Foot_R"]))
    pelvis_world = bpy.data.objects["Pelvis"].matrix_world.translation
    print(f"[TASK4A] Foot world min Z: {foot_min:.6f} m")
    print(f"[TASK4A] Pelvis world: {tuple(round(c, 6) for c in pelvis_world)}")
    if foot_min < -0.02 or foot_min > 0.05:
        raise RuntimeError(f"Feet not near ground Z=0; min Z={foot_min:.6f}")
    pelvis_xy_err = ((pelvis_world.x - start[0]) ** 2 + (pelvis_world.y - start[1]) ** 2) ** 0.5
    if pelvis_xy_err > 0.25:
        raise RuntimeError(f"Pelvis world XY offset {pelvis_xy_err:.4f}m from start waypoint")

    configure_render(config)
    scene = bpy.context.scene
    scene.frame_set(config.frame_start)

    # Frame the character from inside the obstacle-free corridor (clearance >= 2.4m)
    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        cam_obj.location = (start[0] + 1.5, start[1] + 4.5, 1.35)
        target_obj.location = (start[0], start[1], 0.85)
        cam_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        target_obj.keyframe_insert(data_path="location", frame=config.frame_start)
        bpy.context.view_layer.update()

    preview_path = config.character_preview_path
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    print(f"[TASK4A] Preview written: {preview_path}")

    blend_path = config.character_blend_path
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK4A] Prototype blend written: {blend_path}")

    task3_blend = config.blend_file_path
    if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(task3_blend)):
        raise RuntimeError("Refusing to overwrite Task 3 blend path")

    results = {
        "root_location": tuple(root.location),
        "start_waypoint": start,
        "foot_min_z": round(foot_min, 6),
        "part_count": len(REQUIRED_PARTS),
        "blend_path": blend_path,
        "preview_path": preview_path,
        "task3_blend_preserved": os.path.isfile(task3_blend),
    }
    print("[TASK4A] COMPLETED SUCCESSFULLY")
    print("=" * 60)
    return results


if __name__ == "__main__":
    try:
        run_character_prototype()
    except Exception as e:
        print(f"[TASK4A_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
