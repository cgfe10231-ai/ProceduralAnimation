"""Task 6F-A visual acceptance prototype runner: Arm IK and world-space control.

Builds an isolated interactive Blender scene (`output/character_arm_ik_prototype.blend`)
demonstrating the 5-phase visual acceptance timeline for two-bone arm IK:
  Phase 0 (Frames 1..20): Neutral standing rest pose
  Phase 1 (Frames 21..70): Sequential reach (L reaches forward, then R reaches outward)
  Phase 2 (Frames 71..110): Simultaneous bilateral motion without mutual interference
  Phase 3 (Frames 111..150): Fixed wrist position with 3D palm rotation
  Phase 4 (Frames 151..190): Fixed wrist position with elbow swivel via pole target
  Phase 5 (Frames 191..216): Smooth return to default neutral rest pose

Features:
- Concise colored markers on HandIK.L/R and ElbowPole.L/R for immediate 3D visualization.
- Dedicated camera framing upper body and arm motion.
- Fully self-contained .blend: opening and pressing Spacebar in Blender 5.1 plays the animation.
"""

import math
import os
import sys
from typing import Dict, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Vector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.lighting import setup_lighting
from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    DEFAULT_POLE_BACKWARD_OFFSET,
    DEFAULT_POLE_OUTWARD_OFFSET,
    HAND_ROT_CONSTRAINT_NAMES,
    SHOULDER_X_OFFSET,
    WRIST_REST_Z,
    reset_arm_ik,
    set_arm_ik_influence,
    setup_arm_ik,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose
from src.scene import setup_scene


def _get_or_create_material(name: str, diffuse_color: Tuple[float, float, float, float]) -> bpy.types.Material:
    """Create or retrieve a simple colored viewport material."""
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = diffuse_color
        mat.roughness = 0.4
    return mat


def _create_visual_markers(controls: Dict[str, bpy.types.Object]) -> Dict[str, bpy.types.Object]:
    """Create clean, colored visual markers parented to IK and Pole targets."""
    scene = bpy.context.scene
    markers_col = bpy.data.collections.get("Markers")
    if markers_col is None:
        markers_col = bpy.data.collections.new("Markers")
        scene.collection.children.link(markers_col)

    # Material color palette
    mat_hand_l = _get_or_create_material("Mat_Marker_Hand_L", (0.1, 0.5, 0.9, 1.0))   # Blue
    mat_hand_r = _get_or_create_material("Mat_Marker_Hand_R", (0.9, 0.3, 0.1, 1.0))   # Coral Red
    mat_pole_l = _get_or_create_material("Mat_Marker_Pole_L", (0.1, 0.8, 0.8, 1.0))   # Cyan
    mat_pole_r = _get_or_create_material("Mat_Marker_Pole_R", (0.9, 0.8, 0.1, 1.0))   # Yellow

    marker_specs = (
        ("HandIK.L", "Marker_HandIK_L", "CUBE", 0.032, mat_hand_l),
        ("HandIK.R", "Marker_HandIK_R", "CUBE", 0.032, mat_hand_r),
        ("ElbowPole.L", "Marker_ElbowPole_L", "SPHERE", 0.024, mat_pole_l),
        ("ElbowPole.R", "Marker_ElbowPole_R", "SPHERE", 0.024, mat_pole_r),
    )

    markers: Dict[str, bpy.types.Object] = {}
    for parent_name, marker_name, shape, size, mat in marker_specs:
        parent_obj = controls.get(parent_name)
        existing = bpy.data.objects.get(marker_name)
        if existing is not None:
            bpy.data.objects.remove(existing, do_unlink=True)

        mesh = bpy.data.meshes.new(f"{marker_name}_Mesh")
        marker_obj = bpy.data.objects.new(marker_name, mesh)
        markers_col.objects.link(marker_obj)

        if shape == "CUBE":
            # Simple cube geometry centered at origin
            hs = size * 0.5
            verts = [
                (-hs, -hs, -hs), (hs, -hs, -hs), (hs, hs, -hs), (-hs, hs, -hs),
                (-hs, -hs, hs), (hs, -hs, hs), (hs, hs, hs), (-hs, hs, hs),
            ]
            faces = [
                (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5),
            ]
            mesh.from_pydata(verts, [], faces)
        else:
            # Simple octahedron / diamond for sphere marker
            r = size
            verts = [(0, 0, r), (0, 0, -r), (r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0)]
            faces = [
                (0, 2, 4), (0, 4, 3), (0, 3, 5), (0, 5, 2),
                (1, 2, 4), (1, 4, 3), (1, 3, 5), (1, 5, 2),
            ]
            mesh.from_pydata(verts, [], faces)

        mesh.update()
        marker_obj.data.materials.append(mat)

        if parent_obj is not None:
            marker_obj.parent = parent_obj
            marker_obj.matrix_parent_inverse = Matrix.Identity(4)
            marker_obj.location = Vector((0.0, 0.0, 0.0))
            marker_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

        markers[marker_name] = marker_obj

    return markers


def _setup_visual_camera(config: PipelineConfig) -> bpy.types.Object:
    """Create dedicated camera framing character upper body and arms."""
    scene = bpy.context.scene
    cam_col = bpy.data.collections.get("Camera")
    if cam_col is None:
        cam_col = bpy.data.collections.new("Camera")
        scene.collection.children.link(cam_col)

    cam_obj = bpy.data.objects.get("ArmIKCamera")
    if cam_obj is None:
        cam_data = bpy.data.cameras.new("ArmIKCameraData")
        cam_obj = bpy.data.objects.new("ArmIKCamera", cam_data)
        cam_col.objects.link(cam_obj)

    cam_obj.data.lens = 45.0  # 45mm lens for clear perspective without barrel distortion
    scene.camera = cam_obj

    # Position camera front-right at chest height
    cam_obj.location = Vector((1.75, -5.50, 1.55))

    target_obj = bpy.data.objects.get("ArmIKCameraTarget")
    if target_obj is None:
        target_obj = bpy.data.objects.new("ArmIKCameraTarget", None)
        target_obj.empty_display_type = "PLAIN_AXES"
        target_obj.empty_display_size = 0.05
        cam_col.objects.link(target_obj)

    target_obj.location = Vector((0.0, -7.85, 1.25))

    for con in list(cam_obj.constraints):
        cam_obj.constraints.remove(con)
    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target_obj
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    return cam_obj


def generate_arm_ik_visual_prototype(config: Optional[PipelineConfig] = None) -> dict:
    """Generate the 216-frame Arm IK visual acceptance prototype and save .blend file."""
    if config is None:
        config = PipelineConfig()

    print("=" * 74)
    print("TASK 6F-A VISUAL ACCEPTANCE PROTOTYPE GENERATION")
    print("=" * 74)

    # 1. Initialize scene, environment, lighting, character and rig
    setup_scene(config)
    setup_lighting(config)
    build_character(config)
    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = build_rig(config, character_root=root_obj)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    reset_leg_ik(arm_obj)

    # 2. Setup Arm IK with full influence = 1.0 for demonstration
    controls = setup_arm_ik(arm_obj, initial_influence=1.0)
    set_arm_ik_influence(arm_obj, "BOTH", influence=1.0)

    # 3. Create visual colored markers
    markers = _create_visual_markers(controls)

    # 4. Setup camera
    cam = _setup_visual_camera(config)

    # 5. Build Keyframe Animation on Controls
    hand_ik_l = controls["HandIK.L"]
    hand_ik_r = controls["HandIK.R"]
    pole_l = controls["ElbowPole.L"]
    pole_r = controls["ElbowPole.R"]

    # Clear existing animation data
    for obj in (hand_ik_l, hand_ik_r, pole_l, pole_r, arm_obj, root_obj):
        if obj.animation_data:
            obj.animation_data_clear()

    # Timeline keyframe specifications
    # Coordinates in CharacterRoot local space:
    # Root is at (0.0, -8.0, 0.0). Local offsets match world relative to root.
    # Rest positions:
    # L wrist: (-0.24, 0.00, 0.98), R wrist: (0.24, 0.00, 0.98)
    # L pole: (-0.32, -0.40, 1.24), R pole: (0.32, -0.40, 1.24)

    rest_l_pos = Vector((-0.24, 0.00, 0.98))
    rest_r_pos = Vector((0.24, 0.00, 0.98))
    rest_l_rot = Euler((0.0, 0.0, 0.0), "XYZ")
    rest_r_rot = Euler((0.0, 0.0, 0.0), "XYZ")
    rest_l_pole = Vector((-0.32, -0.40, 1.24))
    rest_r_pole = Vector((0.32, -0.40, 1.24))

    # Working chest position for Phases 2, 3, 4:
    work_l_pos = Vector((-0.22, 0.25, 1.28))
    work_r_pos = Vector((0.22, 0.25, 1.28))

    keyframes_data = [
        # Frame, (L_pos, L_rot, L_pole), (R_pos, R_rot, R_pole)
        # ---------------------------------------------------------------------
        # Phase 0: Standing Neutral Rest (Frames 1..20)
        # ---------------------------------------------------------------------
        (1,
         (rest_l_pos, rest_l_rot, rest_l_pole),
         (rest_r_pos, rest_r_rot, rest_r_pole)),
        (20,
         (rest_l_pos, rest_l_rot, rest_l_pole),
         (rest_r_pos, rest_r_rot, rest_r_pole)),

        # ---------------------------------------------------------------------
        # Phase 1: Sequential Reaching (Frames 21..70)
        # Subphase 1A: Left hand reaches forward
        # ---------------------------------------------------------------------
        (35,
         (Vector((-0.24, 0.28, 1.30)), rest_l_rot, Vector((-0.32, -0.38, 1.25))),
         (rest_r_pos, rest_r_rot, rest_r_pole)),
        (45,
         (Vector((-0.24, 0.28, 1.30)), rest_l_rot, Vector((-0.32, -0.38, 1.25))),
         (rest_r_pos, rest_r_rot, rest_r_pole)),

        # Subphase 1B: Left relaxes slightly, Right reaches outward-forward
        (52,
         (Vector((-0.24, 0.10, 1.08)), rest_l_rot, rest_l_pole),
         (rest_r_pos, rest_r_rot, rest_r_pole)),
        (62,
         (Vector((-0.24, 0.10, 1.08)), rest_l_rot, rest_l_pole),
         (Vector((0.40, 0.22, 1.22)), rest_r_rot, Vector((0.46, -0.35, 1.22)))),
        (70,
         (Vector((-0.24, 0.10, 1.08)), rest_l_rot, rest_l_pole),
         (Vector((0.40, 0.22, 1.22)), rest_r_rot, Vector((0.46, -0.35, 1.22)))),

        # ---------------------------------------------------------------------
        # Phase 2: Simultaneous Bilateral Motion without Mutual Interference (Frames 71..110)
        # ---------------------------------------------------------------------
        (88,
         (Vector((-0.18, 0.25, 1.48)), rest_l_rot, Vector((-0.28, -0.35, 1.35))),
         (Vector((0.30, 0.28, 1.12)), rest_r_rot, Vector((0.40, -0.38, 1.15)))),
        (98,
         (Vector((-0.18, 0.25, 1.48)), rest_l_rot, Vector((-0.28, -0.35, 1.35))),
         (Vector((0.30, 0.28, 1.12)), rest_r_rot, Vector((0.40, -0.38, 1.15)))),
        (110,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),

        # ---------------------------------------------------------------------
        # Phase 3: Fixed Wrist Position with 3D Palm Rotation (Frames 111..150)
        # Wrist position stays STRICTLY LOCKED at work_l_pos / work_r_pos
        # ---------------------------------------------------------------------
        (112,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),
        (124,
         (work_l_pos, Euler((math.radians(35.0), math.radians(-25.0), math.radians(40.0)), "XYZ"), rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),
        (136,
         (work_l_pos, Euler((math.radians(-25.0), math.radians(30.0), math.radians(-25.0)), "XYZ"), rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),
        (150,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),

        # ---------------------------------------------------------------------
        # Phase 4: Fixed Wrist Position with Elbow Swivel via Pole Target (Frames 151..190)
        # Right wrist position stays STRICTLY LOCKED at work_r_pos
        # ---------------------------------------------------------------------
        (152,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),
        (165,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, Vector((0.58, -0.25, 1.38)))),  # Elbow wings outward
        (178,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, Vector((0.18, -0.48, 1.05)))),  # Elbow tucks inward
        (190,
         (work_l_pos, rest_l_rot, rest_l_pole),
         (work_r_pos, rest_r_rot, rest_r_pole)),

        # ---------------------------------------------------------------------
        # Phase 5: Smooth Return to Default Neutral Rest Pose (Frames 191..216)
        # ---------------------------------------------------------------------
        (206,
         (rest_l_pos, rest_l_rot, rest_l_pole),
         (rest_r_pos, rest_r_rot, rest_r_pole)),
        (216,
         (rest_l_pos, rest_l_rot, rest_l_pole),
         (rest_r_pos, rest_r_rot, rest_r_pole)),
    ]

    for frame, (l_p, l_r, l_pol), (r_p, r_r, r_pol) in keyframes_data:
        # Left controllers
        hand_ik_l.location = l_p
        hand_ik_l.rotation_euler = l_r
        pole_l.location = l_pol
        hand_ik_l.keyframe_insert(data_path="location", frame=frame)
        hand_ik_l.keyframe_insert(data_path="rotation_euler", frame=frame)
        pole_l.keyframe_insert(data_path="location", frame=frame)

        # Right controllers
        hand_ik_r.location = r_p
        hand_ik_r.rotation_euler = r_r
        pole_r.location = r_pol
        hand_ik_r.keyframe_insert(data_path="location", frame=frame)
        hand_ik_r.keyframe_insert(data_path="rotation_euler", frame=frame)
        pole_r.keyframe_insert(data_path="location", frame=frame)

    # Set smooth BEZIER interpolation on all generated fcurves
    def _ensure_bezier_interpolation(obj: bpy.types.Object) -> None:
        if not (obj.animation_data and obj.animation_data.action):
            return
        act = obj.animation_data.action
        if hasattr(act, "fcurves"):
            for fc in act.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
        if hasattr(act, "layers"):
            for layer in act.layers:
                for strip in layer.strips:
                    for cb in getattr(strip, "channelbags", []):
                        for fc in getattr(cb, "fcurves", []):
                            for kp in fc.keyframe_points:
                                kp.interpolation = "BEZIER"

    for obj in (hand_ik_l, hand_ik_r, pole_l, pole_r):
        _ensure_bezier_interpolation(obj)

    # Set scene timeline properties
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = config.arm_ik_total_frames
    scene.frame_current = 1
    bpy.context.view_layer.update()

    # Save isolated prototype .blend file
    out_blend = config.arm_ik_blend_path
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print(f"[TASK6F-A] Saved isolated Arm IK prototype to: {out_blend}")
    print(f"[TASK6F-A] Timeline: {scene.frame_start}..{scene.frame_end} ({config.arm_ik_total_frames} frames @ 24 FPS = 9.0s)")

    return {
        "blend_path": out_blend,
        "total_frames": config.arm_ik_total_frames,
        "phases": {
            "Phase 0 (Neutral Standing Rest)": "Frames 1..20",
            "Phase 1 (Sequential Reach L then R)": "Frames 21..70",
            "Phase 2 (Simultaneous Bilateral Motion)": "Frames 71..110",
            "Phase 3 (Fixed Wrist 3D Palm Rotation)": "Frames 111..150",
            "Phase 4 (Fixed Wrist Elbow Pole Swivel)": "Frames 151..190",
            "Phase 5 (Return to Neutral Rest)": "Frames 191..216",
        },
    }


if __name__ == "__main__":
    generate_arm_ik_visual_prototype()
