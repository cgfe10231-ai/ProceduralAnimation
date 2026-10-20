"""Task 6G-C Visual Acceptance Prototype: Multi-Limb Contact Geometry, Constraints & Support States.

Generates a standalone, observable Blender scene (`output/contact_model_debug.blend`)
demonstrating all 6 canonical multi-contact support states across a continuous 120-frame timeline:

  - State 1 (Frames 1..15):   Double Stance (Bilateral ground unilateral contacts, normal +Z)
  - State 2 (Frames 25..35):  Single Stance (Left foot locked, right foot swinging free)
  - State 3 (Frames 45..55):  Hand Support / Vault Touch (Foot on ground + Right hand on obstacle top)
  - State 4 (Frames 65..75):  Ground + Vertical Wall Multi-Normal (Foot on ground + Foot on vertical wall -Y)
  - State 5 (Frames 85..95):  Double Hand Grasp Ledge Hang (Bilateral hands grasping ledge bar, feet suspended)
  - State 6 (Frames 105..120): Full Flight Phase (All 4 limbs in air, zero active contacts)

Environment objects in scene:
  - Flat ground plane (Z=0.0)
  - Vault obstacle box (top at Z=0.85)
  - Vertical wall obstacle (facing -Y)
  - Overhead ledge grab bar (Z=1.80)

Visual markers:
  - Contact anchor spheres (Green: Unilateral Ground, Yellow: Wall, Blue: Grasp Ledge, Grey: Free)
  - Surface normal arrows showing outward orientation n_hat
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.lighting import setup_lighting
from src.motion.contact_model import (
    ContactLifecycle,
    ContactRecord,
    ContactType,
    MultiContactState,
    SupportType,
)
from src.rig.arm_ik import (
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import (
    IK_TARGET_NAMES,
    POLE_TARGET_NAMES,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose
from src.scene import setup_scene


# =============================================================================
# Helper Utilities
# =============================================================================

def _get_or_create_material(name: str, diffuse_color: Tuple[float, float, float, float], roughness: float = 0.3) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = diffuse_color
        mat.roughness = roughness
    return mat


def _create_box_mesh(name: str, size: Tuple[float, float, float], location: Tuple[float, float, float], mat: bpy.types.Material) -> bpy.types.Object:
    """Create a simple box mesh with given dimensions and material."""
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    sx, sy, sz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    verts = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj.location = Vector(location)
    obj.data.materials.append(mat)
    return obj


def _create_arrow_marker(name: str, color: Tuple[float, float, float, float], length: float = 0.15) -> bpy.types.Object:
    """Create a small directional arrow pointing along +Z."""
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    obj = bpy.data.objects.new(name, mesh)

    # Simple shaft + tip pyramid
    r = 0.012
    tip_r = 0.03
    tip_start = length * 0.7
    verts = [
        (-r, -r, 0.0), (r, -r, 0.0), (r, r, 0.0), (-r, r, 0.0),
        (-r, -r, tip_start), (r, -r, tip_start), (r, r, tip_start), (-r, r, tip_start),
        (-tip_r, -tip_r, tip_start), (tip_r, -tip_r, tip_start), (tip_r, tip_r, tip_start), (-tip_r, tip_r, tip_start),
        (0.0, 0.0, length),
    ]
    faces = [
        (0, 1, 2, 3), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
        (8, 9, 10, 11),
        (8, 9, 12), (9, 10, 12), (10, 11, 12), (11, 8, 12),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    mat = _get_or_create_material(f"{name}_Mat", color)
    obj.data.materials.append(mat)
    return obj


# =============================================================================
# Scene Setup & Environment
# =============================================================================

def setup_environment() -> Dict[str, bpy.types.Object]:
    """Create environment obstacles for multi-contact demonstration."""
    mat_ground = _get_or_create_material("Mat_Ground", (0.25, 0.28, 0.30, 1.0), roughness=0.8)
    mat_vault = _get_or_create_material("Mat_VaultBox", (0.75, 0.45, 0.25, 1.0), roughness=0.5)
    mat_wall = _get_or_create_material("Mat_Wall", (0.45, 0.50, 0.55, 1.0), roughness=0.6)
    mat_ledge = _get_or_create_material("Mat_LedgeBar", (0.85, 0.85, 0.90, 1.0), roughness=0.2)

    # 1. Ground plane (Z=0, large)
    ground = _create_box_mesh("GroundObstacle", (6.0, 16.0, 0.05), (0.0, -5.0, -0.025), mat_ground)

    # 2. Vault box: positioned at Y = -7.3, X = 0.35, top at Z = 0.85
    # Box dimensions: width 0.60, length 0.80, height 0.85 -> center Z = 0.425
    vault_box = _create_box_mesh("VaultBox", (0.60, 0.80, 0.85), (0.35, -7.30, 0.425), mat_vault)

    # 3. Vertical wall: positioned at Y = -6.2, X = -0.4, facing -Y
    # Dimensions: width 1.2, depth 0.20, height 2.2 -> center Z = 1.10
    wall = _create_box_mesh("VerticalWall", (1.20, 0.20, 2.20), (-0.40, -6.10, 1.10), mat_wall)

    # 4. Ledge grab bar: horizontal bar at Y = -4.8, Z = 1.80
    # Dimensions: width 1.0, depth 0.08, height 0.08
    ledge_bar = _create_box_mesh("LedgeBar", (1.00, 0.08, 0.08), (0.0, -4.80, 1.80), mat_ledge)

    return {
        "ground": ground,
        "vault_box": vault_box,
        "wall": wall,
        "ledge_bar": ledge_bar,
    }


def create_contact_markers() -> Dict[str, Tuple[bpy.types.Object, bpy.types.Object]]:
    """Create visual markers (sphere anchor + normal arrow) for each limb."""
    markers_col = bpy.data.collections.get("ContactMarkers")
    if markers_col is None:
        markers_col = bpy.data.collections.new("ContactMarkers")
        bpy.context.scene.collection.children.link(markers_col)

    mat_green = (0.1, 0.85, 0.2, 1.0)   # Unilateral ground
    mat_yellow = (0.95, 0.85, 0.1, 1.0) # Vertical wall
    mat_blue = (0.15, 0.5, 0.95, 1.0)   # Grasp ledge
    mat_coral = (0.9, 0.35, 0.2, 1.0)   # Hand support

    limb_colors = {
        "foot_L": mat_green,
        "foot_R": mat_green,
        "hand_L": mat_blue,
        "hand_R": mat_coral,
    }

    markers: Dict[str, Tuple[bpy.types.Object, bpy.types.Object]] = {}

    for limb, col in limb_colors.items():
        # Sphere anchor
        mesh = bpy.data.meshes.new(f"Marker_Anchor_{limb}_Mesh")
        obj_sphere = bpy.data.objects.new(f"Marker_Anchor_{limb}", mesh)
        markers_col.objects.link(obj_sphere)

        # Simple 8-vert octahedron
        s = 0.028
        verts = [(0, 0, s), (0, 0, -s), (s, 0, 0), (-s, 0, 0), (0, s, 0), (0, -s, 0)]
        faces = [
            (0, 2, 4), (0, 4, 3), (0, 3, 5), (0, 5, 2),
            (1, 4, 2), (1, 3, 4), (1, 5, 3), (1, 2, 5),
        ]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        mat = _get_or_create_material(f"Mat_Anchor_{limb}", col)
        obj_sphere.data.materials.append(mat)

        # Normal arrow
        obj_arrow = _create_arrow_marker(f"Marker_Normal_{limb}", col, length=0.14)
        markers_col.objects.link(obj_arrow)

        markers[limb] = (obj_sphere, obj_arrow)

    return markers


def update_marker(
    marker_pair: Tuple[bpy.types.Object, bpy.types.Object],
    position: Tuple[float, float, float],
    normal: Tuple[float, float, float],
    visible: bool = True,
    frame: Optional[int] = None,
) -> None:
    """Position and orient anchor sphere and normal arrow at specified frame."""
    obj_sphere, obj_arrow = marker_pair
    pos = Vector(position)
    norm = Vector(normal).normalized() if Vector(normal).length > 1e-6 else Vector((0, 0, 1))

    obj_sphere.location = pos
    obj_arrow.location = pos

    # Align arrow +Z with normal
    rot_quat = Vector((0.0, 0.0, 1.0)).rotation_difference(norm)
    obj_arrow.rotation_mode = "QUATERNION"
    obj_arrow.rotation_quaternion = rot_quat

    scale = Vector((1.0, 1.0, 1.0)) if visible else Vector((0.0001, 0.0001, 0.0001))
    obj_sphere.scale = scale
    obj_arrow.scale = scale

    if frame is not None:
        obj_sphere.keyframe_insert("location", frame=frame)
        obj_sphere.keyframe_insert("scale", frame=frame)
        obj_arrow.keyframe_insert("location", frame=frame)
        obj_arrow.keyframe_insert("rotation_quaternion", frame=frame)
        obj_arrow.keyframe_insert("scale", frame=frame)


# =============================================================================
# Animation Keyframing
# =============================================================================

def build_contact_animation(
    arm: bpy.types.Object,
    root: bpy.types.Object,
    markers: Dict[str, Tuple[bpy.types.Object, bpy.types.Object]],
) -> None:
    """Generate keyframes demonstrating 6 support states across frames 1..120."""
    ik_foot_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_foot_r = bpy.data.objects[IK_TARGET_NAMES["R"]]
    pole_foot_l = bpy.data.objects[POLE_TARGET_NAMES["L"]]
    pole_foot_r = bpy.data.objects[POLE_TARGET_NAMES["R"]]

    ik_hand_l = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
    ik_hand_r = bpy.data.objects[ARM_IK_TARGET_NAMES["R"]]
    pole_hand_l = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]
    pole_hand_r = bpy.data.objects[ARM_POLE_TARGET_NAMES["R"]]

    p_pelvis = arm.pose.bones["pelvis"]

    def _key_all(frame: int) -> None:
        root.keyframe_insert("location", frame=frame)
        root.keyframe_insert("rotation_euler", frame=frame)
        p_pelvis.keyframe_insert("location", frame=frame)
        p_pelvis.keyframe_insert("rotation_euler", frame=frame)
        ik_foot_l.keyframe_insert("location", frame=frame)
        ik_foot_r.keyframe_insert("location", frame=frame)
        ik_hand_l.keyframe_insert("location", frame=frame)
        ik_hand_r.keyframe_insert("location", frame=frame)
        pole_foot_l.keyframe_insert("location", frame=frame)
        pole_foot_r.keyframe_insert("location", frame=frame)
        pole_hand_l.keyframe_insert("location", frame=frame)
        pole_hand_r.keyframe_insert("location", frame=frame)

    # -------------------------------------------------------------------------
    # State 1: Double Stance (Frames 1..15)
    # Character grounded at start position (0, -8.0, 0)
    # Both feet active on flat ground (normal +Z)
    # -------------------------------------------------------------------------
    root.location = Vector((0.0, -8.0, 0.0))
    p_pelvis.location = Vector((0.0, 0.0, 0.0))
    p_pelvis.rotation_euler = Euler((0.0, 0.0, 0.0))

    ik_foot_l.location = Vector((-0.11, -8.0, 0.07))
    ik_foot_r.location = Vector((0.11, -8.0, 0.07))
    pole_foot_l.location = Vector((-0.11, -7.6, 0.45))
    pole_foot_r.location = Vector((0.11, -7.6, 0.45))

    ik_hand_l.location = Vector((-0.24, -8.0, 0.98))
    ik_hand_r.location = Vector((0.24, -8.0, 0.98))
    pole_hand_l.location = Vector((-0.35, -8.2, 1.24))
    pole_hand_r.location = Vector((0.35, -8.2, 1.24))

    for f in (1, 15):
        _key_all(f)
        update_marker(markers["foot_L"], (-0.11, -8.0, 0.0), (0, 0, 1), visible=True, frame=f)
        update_marker(markers["foot_R"], (0.11, -8.0, 0.0), (0, 0, 1), visible=True, frame=f)
        update_marker(markers["hand_L"], (-0.24, -8.0, 0.98), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["hand_R"], (0.24, -8.0, 0.98), (0, 0, 1), visible=False, frame=f)

    # -------------------------------------------------------------------------
    # State 2: Single Stance (Frames 25..35)
    # Left foot grounded; Right foot lifts and swings forward (+Y, +Z)
    # -------------------------------------------------------------------------
    root.location = Vector((0.0, -7.8, 0.0))
    ik_foot_l.location = Vector((-0.11, -7.8, 0.07))
    ik_foot_r.location = Vector((0.11, -7.6, 0.32)) # Swing foot in air
    pole_foot_r.location = Vector((0.11, -7.2, 0.50))

    ik_hand_l.location = Vector((-0.24, -7.6, 1.05))
    ik_hand_r.location = Vector((0.24, -8.0, 0.92))

    for f in (25, 35):
        _key_all(f)
        update_marker(markers["foot_L"], (-0.11, -7.8, 0.0), (0, 0, 1), visible=True, frame=f)
        update_marker(markers["foot_R"], (0.11, -7.6, 0.25), (0, 0, 1), visible=False, frame=f) # Swing foot free
        update_marker(markers["hand_L"], (-0.24, -7.6, 1.05), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["hand_R"], (0.24, -8.0, 0.92), (0, 0, 1), visible=False, frame=f)

    # -------------------------------------------------------------------------
    # State 3: Hand Support / Vault Touch (Frames 45..55)
    # Character plants Right Hand on top of vault box (Z=0.85)
    # Left foot grounded on surface, right foot preparing takeoff
    # -------------------------------------------------------------------------
    root.location = Vector((0.08, -7.5, 0.0))
    p_pelvis.location = Vector((0.0, 0.0, -0.05)) # Lower pelvis slightly
    p_pelvis.rotation_euler = Euler((math.radians(12.0), 0.0, 0.0))

    ik_foot_l.location = Vector((-0.11, -7.65, 0.07))
    ik_foot_r.location = Vector((0.15, -7.45, 0.15))
    ik_hand_r.location = Vector((0.30, -7.30, 0.85)) # Right hand on vault box top
    pole_hand_r.location = Vector((0.45, -7.45, 1.05))
    ik_hand_l.location = Vector((-0.20, -7.40, 1.15))

    for f in (45, 55):
        _key_all(f)
        update_marker(markers["foot_L"], (-0.11, -7.65, 0.0), (0, 0, 1), visible=True, frame=f)
        update_marker(markers["foot_R"], (0.15, -7.45, 0.08), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["hand_R"], (0.30, -7.30, 0.85), (0, 0, 1), visible=True, frame=f) # Vault touch
        update_marker(markers["hand_L"], (-0.20, -7.40, 1.15), (0, 0, 1), visible=False, frame=f)

    # -------------------------------------------------------------------------
    # State 4: Ground + Vertical Wall Multi-Normal (Frames 65..75)
    # Left foot on ground (normal +Z), Right foot plants against vertical wall (normal -Y)
    # Non-coplanar multi-surface contact
    # -------------------------------------------------------------------------
    root.location = Vector((-0.25, -6.65, 0.0))
    p_pelvis.location = Vector((0.0, 0.0, -0.08))
    p_pelvis.rotation_euler = Euler((math.radians(-8.0), 0.0, 0.0))

    ik_foot_l.location = Vector((-0.35, -6.75, 0.07))  # Ground stance
    # Wall is at Y = -6.20. Foot sole touches Y = -6.20, ankle at Y = -6.27, Z = 0.55
    ik_foot_r.location = Vector((-0.15, -6.27, 0.55))
    pole_foot_r.location = Vector((-0.15, -6.50, 0.75))

    ik_hand_l.location = Vector((-0.45, -6.65, 1.05))
    ik_hand_r.location = Vector((-0.05, -6.60, 1.10))

    for f in (65, 75):
        _key_all(f)
        update_marker(markers["foot_L"], (-0.35, -6.75, 0.0), (0, 0, 1), visible=True, frame=f) # Ground
        update_marker(markers["foot_R"], (-0.15, -6.20, 0.55), (0, -1, 0), visible=True, frame=f) # Vertical Wall!
        update_marker(markers["hand_L"], (-0.45, -6.65, 1.05), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["hand_R"], (-0.05, -6.60, 1.10), (0, 0, 1), visible=False, frame=f)

    # -------------------------------------------------------------------------
    # State 5: Double Hand Grasp Ledge Hang (Frames 85..95)
    # Character suspended by both hands grasping overhead bar (Z=1.80)
    # Bilateral 3D grasp constraints, feet suspended freely in air
    # -------------------------------------------------------------------------
    # Character hangs down from Z=1.80 ledge: root elevated to Z=0.50
    root.location = Vector((0.0, -4.80, 0.50))
    p_pelvis.location = Vector((0.0, 0.0, 0.0))
    p_pelvis.rotation_euler = Euler((0.0, 0.0, 0.0))

    # Ledge bar is at Y = -4.80, Z = 1.80
    ik_hand_l.location = Vector((-0.22, -4.80, 1.80))
    ik_hand_r.location = Vector((0.22, -4.80, 1.80))
    pole_hand_l.location = Vector((-0.30, -4.95, 1.55))
    pole_hand_r.location = Vector((0.30, -4.95, 1.55))

    # Feet dangling freely off ground (ground is Z=0, feet at Z=0.57)
    ik_foot_l.location = Vector((-0.11, -4.80, 0.57))
    ik_foot_r.location = Vector((0.11, -4.80, 0.57))
    pole_foot_l.location = Vector((-0.11, -4.50, 0.75))
    pole_foot_r.location = Vector((0.11, -4.50, 0.75))

    for f in (85, 95):
        _key_all(f)
        update_marker(markers["hand_L"], (-0.22, -4.80, 1.80), (0, 1, 0), visible=True, frame=f) # Ledge grasp
        update_marker(markers["hand_R"], (0.22, -4.80, 1.80), (0, 1, 0), visible=True, frame=f) # Ledge grasp
        update_marker(markers["foot_L"], (-0.11, -4.80, 0.50), (0, 0, 1), visible=False, frame=f) # Suspended
        update_marker(markers["foot_R"], (0.11, -4.80, 0.50), (0, 0, 1), visible=False, frame=f) # Suspended

    # -------------------------------------------------------------------------
    # State 6: Full Flight Phase (Frames 105..120)
    # Character released from ledge in mid-air ballistic trajectory (Z=0.75)
    # All 4 limbs free, zero active contacts
    # -------------------------------------------------------------------------
    root.location = Vector((0.0, -3.90, 0.75))
    p_pelvis.location = Vector((0.0, 0.0, 0.0))
    p_pelvis.rotation_euler = Euler((math.radians(-15.0), 0.0, 0.0))

    ik_hand_l.location = Vector((-0.26, -3.85, 1.30))
    ik_hand_r.location = Vector((0.26, -3.85, 1.30))
    ik_foot_l.location = Vector((-0.14, -4.05, 0.70))
    ik_foot_r.location = Vector((0.14, -3.95, 0.85))

    for f in (105, 120):
        _key_all(f)
        update_marker(markers["hand_L"], (-0.26, -3.85, 1.30), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["hand_R"], (0.26, -3.85, 1.30), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["foot_L"], (-0.14, -4.05, 0.63), (0, 0, 1), visible=False, frame=f)
        update_marker(markers["foot_R"], (0.14, -3.95, 0.78), (0, 0, 1), visible=False, frame=f)


# =============================================================================
# Main Prototype Runner
# =============================================================================

def run_prototype() -> str:
    print("================================================================================")
    print("Task 6G-C Visual Prototype: Contact Model & Support States")
    print("================================================================================")

    # 1. Clean scene setup
    cfg = PipelineConfig()
    setup_scene(cfg)
    setup_lighting(cfg)

    # 2. Setup environment obstacles
    obstacles = setup_environment()
    print(f"[SCENE] Created {len(obstacles)} environment obstacles (Ground, VaultBox, Wall, LedgeBar)")

    # 3. Build character and rig
    char_objs = build_character(cfg)
    arm_obj = build_rig(cfg)
    bind_character_to_rig(arm_obj, char_objs)
    root_obj = arm_obj.parent or bpy.data.objects.get("CharacterRoot")

    # 4. Configure IK solvers
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj, initial_influence=1.0)
    print("[RIG] Configured Leg IK and Arm IK with full active influence")

    # 5. Create visual markers
    markers = create_contact_markers()
    print("[MARKERS] Created contact anchor spheres and normal arrows for all 4 limbs")

    # 6. Build 6-state continuous timeline animation (1..120)
    build_contact_animation(arm_obj, root_obj, markers)

    # 7. Configure scene timeline and frame camera
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 120
    scene.frame_current = 1

    # Camera placement for wide side-angle overview
    cam = bpy.data.objects.get("Camera")
    if cam is not None:
        cam.location = Vector((2.8, -10.5, 2.2))
        cam.rotation_euler = Euler((math.radians(72.0), 0.0, math.radians(28.0)), "XYZ")

    # 8. Save output .blend
    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    blend_path = os.path.join(output_dir, "contact_model_debug.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    print(f"\n[PROTOTYPE] Successfully created: {blend_path}")
    print("Timeline Navigation Guide:")
    print("  - Frames 1..15:   State 1: Double Stance (Ground flat contacts, +Z normals)")
    print("  - Frames 25..35:  State 2: Single Stance (Left foot locked, right foot swinging free)")
    print("  - Frames 45..55:  State 3: Hand Support / Vault Touch (Right hand on vault box)")
    print("  - Frames 65..75:  State 4: Ground + Vertical Wall Multi-Normal (+Z ground, -Y wall)")
    print("  - Frames 85..95:  State 5: Double Hand Grasp Ledge Hang (Ledge bar grasp at Z=1.80m)")
    print("  - Frames 105..120: State 6: Full Flight Phase (All limbs free in mid-air)")
    print("================================================================================")
    return blend_path


if __name__ == "__main__":
    run_prototype()
