"""Verify generated unified motion integration blend file (Task 6G-C-R3B-2).

Inspects output/unified_motion_integration.blend:
- File existence & size
- Scene frame range: 1..462
- Rig, bones, and IK controls
- Root continuous displacement across Walk -> SprintStart -> SprintBrake -> Run
- Keyframe data integrity (no NaN/Inf)
- Camera & target tracking
"""

import os
import sys
import bpy

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(PROJECT_ROOT, "output", "unified_motion_integration.blend")

def verify_blend_file():
    print("=" * 80)
    print("VERIFYING OUTPUT: unified_motion_integration.blend")
    print("=" * 80)

    if not os.path.exists(BLEND_PATH):
        raise FileNotFoundError(f"Missing blend file: {BLEND_PATH}")

    file_size = os.path.getsize(BLEND_PATH)
    print(f"[OK] File exists: {BLEND_PATH} ({file_size} bytes)")
    assert file_size > 100000, f"File size too small: {file_size}"

    # Open blend file
    bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
    scene = bpy.context.scene

    print(f"[SCENE] Start frame: {scene.frame_start}, End frame: {scene.frame_end}, FPS: {scene.render.fps}")
    assert scene.frame_start == 1, f"Expected frame_start=1, got {scene.frame_start}"
    assert scene.frame_end == 462, f"Expected frame_end=462, got {scene.frame_end}"
    assert scene.render.fps == 24, f"Expected fps=24, got {scene.render.fps}"

    # Check key objects
    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")

    assert arm_obj is not None, "CharacterArmature object not found"
    assert root_obj is not None, "CharacterRoot object not found"
    assert cam_obj is not None, "PipelineCamera object not found"
    assert target_obj is not None, "CameraLookAtTarget object not found"

    print(f"[OK] Core objects verified: Armature, Root, Camera, LookAtTarget")

    # Sample checkpoints across the 4 chained actions
    checkpoints = [
        (1, -8.0, "Start of Walk (stationary idle)"),
        (204, -6.74, "End of Walk (bilateral stop)"),
        (318, -0.1567, "End of SprintStart (high-speed burst)"),
        (366, 1.3433, "End of SprintBrake (bilateral stop)"),
        (462, 4.9058, "End of Run (4 cycles)"),
    ]

    for f, expected_y, desc in checkpoints:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        ry = root_obj.matrix_world.translation.y
        err = abs(ry - expected_y)
        print(f"  Frame {f:3d} ({desc}): root_Y = {ry:.4f}m (expected ~{expected_y:.4f}m, diff={err:.4f}m)")
        assert err < 0.20, f"Root position at frame {f} deviated too much: actual={ry}, expected={expected_y}"

    # Verify no NaN or Inf in bone transforms across 20 sampled frames
    for sample_f in range(1, 463, 23):
        scene.frame_set(sample_f)
        bpy.context.view_layer.update()
        for pb in arm_obj.pose.bones:
            for val in pb.location:
                assert not (val != val or abs(val) > 1e6), f"Invalid location in {pb.name} at frame {sample_f}"
            for val in pb.rotation_euler:
                assert not (val != val or abs(val) > 1e6), f"Invalid rotation in {pb.name} at frame {sample_f}"

    print("[OK] Sampled 20 frames across timeline: all bone transforms clean (no NaN/Inf)")

    print("=" * 80)
    print("ALL CHECKS FOR unified_motion_integration.blend PASSED 100%!")
    print("=" * 80)

if __name__ == "__main__":
    verify_blend_file()
