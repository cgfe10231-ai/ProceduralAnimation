"""Task 6G-C Visual Prototype: Multi-Limb Contact Geometry, Constraints & Support States.

Fully reworked to address visual acceptance failures:
1. Strict orientation alignment: Character strictly faces forward (+Y) toward obstacles
   (dot product of front vector with target vector >= 0.98 across all segments).
2. Natural human resting and support postures:
   - Double stance: hands naturally hang beside torso (wrists >= 0.40m below shoulders, Z=0.98m),
     feet flat on ground (Z=0.0m).
   - Single stance: pelvis shifts over grounded foot, swing foot lifted with knee flexed.
   - Vault touch: character crouches forward, right hand plants onto obstacle top surface (Z=1.05m).
   - Foot on wall: character faces wall directly (+Y), right foot planted flat against vertical wall (Y=-4.00m).
   - Ledge hang: bilateral hands grasp horizontal bar at Z=1.95m, feet suspended in air.
   - Flight: dynamic airborne running stride in mid-air (Z=0.40m), 0 contacts.
3. Driven 100% by WholeBodyController:
   - Proper world-to-parent local coordinate transformations for HandIK and FootIK empties.
   - Native Blender two-bone leg IK and arm IK evaluated and keyframed at every frame.
   - Discrete 30-frame debugging segments (Frames 1..180) with smooth, physically consistent
     intra-segment transitions (no sudden teleports or limb flipping).
   - Contact anchor spheres and outward normal arrows clearly visible for active contacts.
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
from src.motion.whole_body_controller import (
    WholeBodyController,
    WholeBodyControlTargets,
)
from src.rig.arm_ik import (
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    setup_arm_ik,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import (
    IK_TARGET_NAMES,
    POLE_TARGET_NAMES,
    setup_leg_ik,
)
from src.scene import setup_scene


# =============================================================================
# Helper Utilities
# =============================================================================

def _get_or_create_material(
    name: str,
    diffuse_color: Tuple[float, float, float, float],
    roughness: float = 0.4,
) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = diffuse_color
        mat.roughness = roughness
    return mat


def _create_box_mesh(
    name: str,
    size: Tuple[float, float, float],
    location: Tuple[float, float, float],
    mat: bpy.types.Material,
) -> bpy.types.Object:
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


def _create_arrow_marker(name: str, color: Tuple[float, float, float, float], length: float = 0.16) -> bpy.types.Object:
    """Create a directional arrow mesh pointing along +Z."""
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    obj = bpy.data.objects.new(name, mesh)

    r = 0.012
    tip_r = 0.032
    tip_start = length * 0.65
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
# Scene Environment Setup
# =============================================================================

def setup_environment() -> Dict[str, bpy.types.Object]:
    """Create environment surfaces aligned with the 6 demonstration segments."""
    mat_ground = _get_or_create_material("Mat_Ground", (0.28, 0.30, 0.32, 1.0), roughness=0.8)
    mat_vault = _get_or_create_material("Mat_VaultBox", (0.85, 0.45, 0.20, 1.0), roughness=0.5)
    mat_wall = _get_or_create_material("Mat_Wall", (0.45, 0.52, 0.58, 1.0), roughness=0.6)
    mat_ledge = _get_or_create_material("Mat_LedgeBar", (0.80, 0.82, 0.88, 1.0), roughness=0.2)

    # 1. Continuous Ground Obstacle (Z=0.0 surface)
    ground = _create_box_mesh("GroundObstacle", (6.0, 16.0, 0.06), (0.0, -4.50, -0.03), mat_ground)

    # 2. Vault Box for Segment 3 (character at Y=-5.85, hand plants on top at Z=1.05m)
    # Box dimensions: width 0.60, length 0.60, height 1.05 -> center Z = 0.525
    vault_box = _create_box_mesh("VaultBox", (0.60, 0.60, 1.05), (0.24, -5.75, 0.525), mat_vault)

    # 3. Vertical Wall for Segment 4 (character at Y=-4.50, foot plants against Y=-4.00 wall)
    # Front face at Y=-4.00 (facing -Y). Dimensions: width 1.80, depth 0.20, height 2.40 -> center Y=-3.90, Z=1.20
    wall = _create_box_mesh("VerticalWall", (1.80, 0.20, 2.40), (0.0, -3.90, 1.20), mat_wall)

    # 4. Overhead Ledge Bar for Segment 5 (character hangs at Y=-2.45, bar at Z=1.95m)
    # Dimensions: width 1.60, depth 0.08, height 0.08 -> center Y=-2.45, Z=1.95
    ledge_bar = _create_box_mesh("LedgeBar", (1.60, 0.08, 0.08), (0.0, -2.45, 1.95), mat_ledge)

    return {
        "ground": ground,
        "vault_box": vault_box,
        "wall": wall,
        "ledge_bar": ledge_bar,
    }


def create_contact_markers() -> Dict[str, Tuple[bpy.types.Object, bpy.types.Object]]:
    """Create anchor sphere and normal arrow for all 4 limbs."""
    markers_col = bpy.data.collections.get("ContactMarkers")
    if markers_col is None:
        markers_col = bpy.data.collections.new("ContactMarkers")
        bpy.context.scene.collection.children.link(markers_col)

    palette = {
        "foot_L": (0.15, 0.85, 0.25, 1.0),  # Green: ground unilateral
        "foot_R": (0.15, 0.85, 0.25, 1.0),  # Green: ground / Yellow for wall
        "hand_L": (0.15, 0.55, 0.95, 1.0),  # Blue: grasp ledge
        "hand_R": (0.95, 0.45, 0.15, 1.0),  # Orange/Coral: vault touch
    }

    markers: Dict[str, Tuple[bpy.types.Object, bpy.types.Object]] = {}
    for limb, col in palette.items():
        # Octahedron anchor sphere
        mesh = bpy.data.meshes.new(f"Marker_Anchor_{limb}_Mesh")
        obj_sphere = bpy.data.objects.new(f"Marker_Anchor_{limb}", mesh)
        markers_col.objects.link(obj_sphere)

        s = 0.035
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
        obj_arrow = _create_arrow_marker(f"Marker_Normal_{limb}", col, length=0.16)
        markers_col.objects.link(obj_arrow)

        markers[limb] = (obj_sphere, obj_arrow)

    return markers


# =============================================================================
# Pose Definition & Smooth Interpolation
# =============================================================================

def _smoothstep(t: float) -> float:
    """Cubic smoothstep interpolation factor in [0.0, 1.0]."""
    clamped = max(0.0, min(1.0, t))
    return clamped * clamped * (3.0 - 2.0 * clamped)


def _lerp_vec(v0: Tuple[float, float, float], v1: Tuple[float, float, float], t: float) -> Tuple[float, float, float]:
    s = _smoothstep(t)
    return (
        v0[0] + (v1[0] - v0[0]) * s,
        v0[1] + (v1[1] - v0[1]) * s,
        v0[2] + (v1[2] - v0[2]) * s,
    )


def _lerp_rot(r0: Optional[Tuple[float, float, float]], r1: Optional[Tuple[float, float, float]], t: float) -> Optional[Tuple[float, float, float]]:
    if r0 is None and r1 is None:
        return None
    r0_val = r0 or (0.0, 0.0, 0.0)
    r1_val = r1 or (0.0, 0.0, 0.0)
    return _lerp_vec(r0_val, r1_val, t)


def interpolate_targets(t0: WholeBodyControlTargets, t1: WholeBodyControlTargets, progress: float) -> WholeBodyControlTargets:
    """Interpolate between two WholeBodyControlTargets smoothly."""
    out = WholeBodyControlTargets()
    out.root_position = _lerp_vec(t0.root_position or (0, 0, 0), t1.root_position or (0, 0, 0), progress)
    out.root_yaw_deg = (t0.root_yaw_deg or 0.0) + ((t1.root_yaw_deg or 0.0) - (t0.root_yaw_deg or 0.0)) * _smoothstep(progress)

    p0 = t0.pelvis_location or (0, 0, 0)
    p1 = t1.pelvis_location or (0, 0, 0)
    out.pelvis_location = _lerp_vec(p0, p1, progress)

    out.spine_rotation_deg = _lerp_rot(t0.spine_rotation_deg, t1.spine_rotation_deg, progress)
    out.neck_rotation_deg = _lerp_rot(t0.neck_rotation_deg, t1.neck_rotation_deg, progress)
    out.head_rotation_deg = _lerp_rot(t0.head_rotation_deg, t1.head_rotation_deg, progress)

    # Foot L
    fl0 = t0.foot_L
    fl1 = t1.foot_L
    if fl0 and fl1:
        out.set_foot(
            "L",
            target_world_xyz=_lerp_vec(fl0.target_world_xyz, fl1.target_world_xyz, progress),
            rotation_deg=_lerp_rot(fl0.target_rotation_deg, fl1.target_rotation_deg, progress),
            is_locked=fl1.is_locked if progress >= 0.5 else fl0.is_locked,
        )

    # Foot R
    fr0 = t0.foot_R
    fr1 = t1.foot_R
    if fr0 and fr1:
        out.set_foot(
            "R",
            target_world_xyz=_lerp_vec(fr0.target_world_xyz, fr1.target_world_xyz, progress),
            rotation_deg=_lerp_rot(fr0.target_rotation_deg, fr1.target_rotation_deg, progress),
            is_locked=fr1.is_locked if progress >= 0.5 else fr0.is_locked,
        )

    # Hand L
    hl0 = t0.hand_L
    hl1 = t1.hand_L
    if hl0 and hl1:
        out.set_hand(
            "L",
            target_world_xyz=_lerp_vec(hl0.target_world_xyz, hl1.target_world_xyz, progress),
            rotation_deg=_lerp_rot(hl0.target_rotation_deg, hl1.target_rotation_deg, progress),
        )

    # Hand R
    hr0 = t0.hand_R
    hr1 = t1.hand_R
    if hr0 and hr1:
        out.set_hand(
            "R",
            target_world_xyz=_lerp_vec(hr0.target_world_xyz, hr1.target_world_xyz, progress),
            rotation_deg=_lerp_rot(hr0.target_rotation_deg, hr1.target_rotation_deg, progress),
        )

    return out


# =============================================================================
# Execution & Keyframe Dispatch
# =============================================================================

def apply_and_keyframe_targets(
    controller: WholeBodyController,
    targets: WholeBodyControlTargets,
    frame: int,
    multi_contact: Optional[MultiContactState] = None,
    markers: Optional[Dict[str, Tuple[bpy.types.Object, bpy.types.Object]]] = None,
) -> None:
    """Execute whole-body controller dispatch and insert keyframes for scene playback."""
    # 1. Execute whole-body solver dispatch
    controller.execute_frame(targets)

    # 2. Keyframe root and pelvis
    root = controller.root_obj
    arm = controller.armature_obj

    root.keyframe_insert("location", frame=frame)
    root.keyframe_insert("rotation_euler", frame=frame)

    p_pelvis = arm.pose.bones.get("pelvis")
    if p_pelvis:
        p_pelvis.keyframe_insert("location", frame=frame)
        p_pelvis.keyframe_insert("rotation_euler", frame=frame)

    for b_name in ("spine", "neck", "head", "shoulder.L", "shoulder.R"):
        pb = arm.pose.bones.get(b_name)
        if pb:
            pb.keyframe_insert("rotation_euler", frame=frame)

    # 3. Keyframe IK target objects
    for side in ("L", "R"):
        ik_h = bpy.data.objects.get(ARM_IK_TARGET_NAMES[side])
        pole_h = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[side])
        if ik_h:
            ik_h.keyframe_insert("location", frame=frame)
            ik_h.keyframe_insert("rotation_euler", frame=frame)
        if pole_h:
            pole_h.keyframe_insert("location", frame=frame)

        ik_f = bpy.data.objects.get(IK_TARGET_NAMES[side])
        pole_f = bpy.data.objects.get(POLE_TARGET_NAMES[side])
        if ik_f:
            ik_f.keyframe_insert("location", frame=frame)
            ik_f.keyframe_insert("rotation_euler", frame=frame)
        if pole_f:
            pole_f.keyframe_insert("location", frame=frame)

    # 4. Keyframe visual contact markers
    if markers and multi_contact:
        for limb, (sph, arr) in markers.items():
            crec = multi_contact.contacts.get(limb)
            if crec and crec.is_active:
                pos = Vector(crec.world_anchor)
                norm = Vector(crec.surface_normal).normalized()
                sph.location = pos
                arr.location = pos
                arr.rotation_mode = "QUATERNION"
                arr.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(norm)
                sph.scale = Vector((1.0, 1.0, 1.0))
                arr.scale = Vector((1.0, 1.0, 1.0))
            else:
                sph.scale = Vector((0.0001, 0.0001, 0.0001))
                arr.scale = Vector((0.0001, 0.0001, 0.0001))

            sph.keyframe_insert("location", frame=frame)
            sph.keyframe_insert("scale", frame=frame)
            arr.keyframe_insert("location", frame=frame)
            arr.keyframe_insert("rotation_quaternion", frame=frame)
            arr.keyframe_insert("scale", frame=frame)


# =============================================================================
# The 6 Canonical Demonstration Target Specifications
# =============================================================================

def build_segment_specifications() -> List[Tuple[str, WholeBodyControlTargets, WholeBodyControlTargets, MultiContactState, int, int]]:
    """Define the 6 distinct canonical poses with start/hold targets and contact states."""

    # -------------------------------------------------------------------------
    # 1. Double Stance (Frames 1..30)
    # -------------------------------------------------------------------------
    t1 = WholeBodyControlTargets()
    t1.root_position = (0.0, -8.0, 0.0)
    t1.root_yaw_deg = 0.0
    t1.set_foot("L", (-0.11, -8.0, 0.07), is_locked=True)
    t1.set_foot("R", (0.11, -8.0, 0.07), is_locked=True)
    t1.set_hand("L", (-0.24, -8.0, 0.98), rotation_deg=(-90.0, 0.0, 0.0))
    t1.set_hand("R", (0.24, -8.0, 0.98), rotation_deg=(-90.0, 0.0, 0.0))

    mc1 = MultiContactState({
        "foot_L": ContactRecord("c_fl", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.0), (0, 0, 1)),
        "foot_R": ContactRecord("c_fr", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, -8.0, 0.0), (0, 0, 1)),
    })

    # -------------------------------------------------------------------------
    # 2. Single Stance (Frames 31..60)
    # -------------------------------------------------------------------------
    t2 = WholeBodyControlTargets()
    t2.root_position = (0.0, -8.0, 0.0)
    t2.root_yaw_deg = 0.0
    t2.pelvis_location = (-0.015, -0.01, 0.0)
    t2.set_foot("L", (-0.11, -8.0, 0.07), is_locked=True)
    t2.set_foot("R", (0.11, -7.85, 0.28), is_locked=False)
    t2.set_hand("L", (-0.24, -8.05, 0.98), rotation_deg=(-85.0, 0.0, 0.0))
    t2.set_hand("R", (0.24, -7.95, 1.00), rotation_deg=(-80.0, 0.0, 0.0))

    mc2 = MultiContactState({
        "foot_L": ContactRecord("c_fl", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.0), (0, 0, 1)),
        "foot_R": ContactRecord("c_fr", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.RELEASED, (0.11, -7.85, 0.21), (0, 0, 1)),
    })

    # -------------------------------------------------------------------------
    # 3. Vault Touch (Frames 61..90)
    # Character at Y=-5.85, right hand plants on VaultBox top (Z=1.05m) at Y=-5.75
    # -------------------------------------------------------------------------
    t3 = WholeBodyControlTargets()
    t3.root_position = (0.05, -5.85, 0.0)
    t3.root_yaw_deg = 0.0
    t3.pelvis_location = (0.0, -0.05, 0.0)
    t3.spine_rotation_deg = (12.0, 0.0, 0.0)
    t3.set_foot("L", (-0.11, -5.85, 0.07), is_locked=True)
    t3.set_foot("R", (0.13, -5.95, 0.07), is_locked=True)
    t3.set_hand("R", (0.24, -5.75, 1.05), rotation_deg=(-15.0, 0.0, 0.0))
    t3.set_hand("L", (-0.22, -5.85, 1.05), rotation_deg=(-60.0, 0.0, 0.0))

    mc3 = MultiContactState({
        "foot_L": ContactRecord("c_fl", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -5.85, 0.0), (0, 0, 1)),
        "hand_R": ContactRecord("c_hr", "hand_R", "vault_box", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.24, -5.75, 1.05), (0, 0, 1)),
    })

    # -------------------------------------------------------------------------
    # 4. Foot on Wall (Frames 91..120)
    # Character at Y=-4.50 facing +Y directly at VerticalWall (Y=-4.00)
    # Right foot planted flat against vertical wall surface
    # -------------------------------------------------------------------------
    t4 = WholeBodyControlTargets()
    t4.root_position = (0.0, -4.50, 0.0)
    t4.root_yaw_deg = 0.0
    t4.pelvis_location = (0.0, -0.04, 0.0)
    t4.spine_rotation_deg = (8.0, 0.0, 0.0)
    t4.set_foot("L", (-0.11, -4.55, 0.07), is_locked=True)
    t4.set_foot("R", (0.11, -4.07, 0.45), rotation_deg=(-20.0, 0.0, 0.0))
    t4.set_hand("L", (-0.22, -4.42, 1.15), rotation_deg=(-45.0, 0.0, 0.0))
    t4.set_hand("R", (0.22, -4.38, 1.20), rotation_deg=(-40.0, 0.0, 0.0))

    mc4 = MultiContactState({
        "foot_L": ContactRecord("c_fl", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -4.55, 0.0), (0, 0, 1)),
        "foot_R": ContactRecord("c_fr", "foot_R", "wall", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, -4.00, 0.45), (0, -1, 0)),
    })

    # -------------------------------------------------------------------------
    # 5. Ledge Hang (Frames 121..150)
    # Character suspended at Y=-2.45, grasping horizontal bar at Z=1.95m
    # -------------------------------------------------------------------------
    t5 = WholeBodyControlTargets()
    t5.root_position = (0.0, -2.45, 0.08)
    t5.root_yaw_deg = 0.0
    t5.set_foot("L", (-0.11, -2.45, 0.25), is_locked=False)
    t5.set_foot("R", (0.11, -2.45, 0.25), is_locked=False)
    t5.set_hand("L", (-0.24, -2.45, 1.95), rotation_deg=(0.0, 0.0, 0.0))
    t5.set_hand("R", (0.24, -2.45, 1.95), rotation_deg=(0.0, 0.0, 0.0))

    mc5 = MultiContactState({
        "hand_L": ContactRecord("c_hl", "hand_L", "ledge_bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (-0.24, -2.45, 1.95), (0, 0, 1)),
        "hand_R": ContactRecord("c_hr", "hand_R", "ledge_bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (0.24, -2.45, 1.95), (0, 0, 1)),
    })

    # -------------------------------------------------------------------------
    # 6. Flight Phase (Frames 151..180)
    # Ballistic airborne stride at Y=-1.00, Z=0.40m, 0 active contacts
    # -------------------------------------------------------------------------
    t6 = WholeBodyControlTargets()
    t6.root_position = (0.0, -1.00, 0.40)
    t6.root_yaw_deg = 0.0
    t6.spine_rotation_deg = (8.0, 0.0, 0.0)
    t6.set_foot("L", (-0.13, -1.15, 0.65), is_locked=False, rotation_deg=(-10.0, 0.0, 0.0))
    t6.set_foot("R", (0.13, -0.90, 0.75), is_locked=False)
    t6.set_hand("L", (-0.22, -0.88, 1.55), rotation_deg=(-30.0, 0.0, 0.0))
    t6.set_hand("R", (0.22, -1.12, 1.50), rotation_deg=(-65.0, 0.0, 0.0))

    mc6 = MultiContactState({})

    # Return list of segments: (name, start_target, hold_target, contact_state, f_start, f_end)
    # For Segment 1: start is t1, hold is t1
    # For Segments 2..6: transition from previous hold target to new hold target over 10 frames
    return [
        ("Double Stance", t1, t1, mc1, 1, 30),
        ("Single Stance", t1, t2, mc2, 31, 60),
        ("Vault Touch", t2, t3, mc3, 61, 90),
        ("Foot on Wall", t3, t4, mc4, 91, 120),
        ("Ledge Hang", t4, t5, mc5, 121, 150),
        ("Flight Phase", t5, t6, mc6, 151, 180),
    ]


# =============================================================================
# Prototype Generation Pipeline
# =============================================================================

def generate_contact_model_prototype(config: Optional[PipelineConfig] = None) -> str:
    print("================================================================================")
    print("Task 6G-C Visual Prototype: Contact Model & Support States")
    print("================================================================================")

    if config is None:
        config = PipelineConfig()

    # 1. Clean scene setup
    setup_scene(config)
    setup_lighting(config)

    # 2. Setup environment obstacles
    obstacles = setup_environment()
    print(f"[SCENE] Created {len(obstacles)} environment obstacles (Ground, VaultBox, Wall, LedgeBar)")

    # 3. Build character and rig
    char_objs = build_character(config)
    arm_obj = build_rig(config)
    bind_character_to_rig(arm_obj, char_objs)

    # 4. Configure IK solvers
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj, initial_influence=1.0)
    print("[RIG] Configured Leg IK and Arm IK with full active influence")

    # 5. Initialize WholeBodyController
    controller = WholeBodyController(armature_obj=arm_obj)
    print("[CONTROLLER] WholeBodyController initialized and bound to CharacterArmature")

    # 6. Create visual markers
    markers = create_contact_markers()
    print("[MARKERS] Created contact anchor spheres and normal arrows for all 4 limbs")

    # 7. Generate timeline keyframes across 6 distinct segments
    segments = build_segment_specifications()
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 180

    for name, t_start, t_hold, mc_state, f_start, f_end in segments:
        trans_duration = 10  # 10 frames smooth transition, 20 frames stable hold
        f_hold_start = f_start + trans_duration

        print(f"[TIMELINE] Generating Segment '{name}' (Frames {f_start}..{f_end}):")
        print(f"  - Transition: Frames {f_start}..{f_hold_start - 1}")
        print(f"  - Stable Hold: Frames {f_hold_start}..{f_end}")

        for frame in range(f_start, f_end + 1):
            scene.frame_set(frame)
            if frame < f_hold_start:
                alpha = (frame - f_start) / float(trans_duration)
                targets_f = interpolate_targets(t_start, t_hold, alpha)
            else:
                targets_f = t_hold

            apply_and_keyframe_targets(controller, targets_f, frame, mc_state, markers)

    # 8. Frame camera to clearly view the action
    cam = bpy.data.objects.get("Camera")
    if cam is not None:
        cam.location = Vector((3.4, -5.5, 2.0))
        cam.rotation_euler = Euler((math.radians(74.0), 0.0, math.radians(32.0)), "XYZ")

    # 9. Save output .blend
    scene.frame_set(1)
    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    blend_path = os.path.join(output_dir, "contact_model_debug.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

    print(f"\n[PROTOTYPE] Successfully created: {blend_path}")
    print("Timeline Navigation Guide:")
    print("  - Segment 1 (Frames 1..30):   Double Stance (Bilateral ground contacts, Z=0.0m, +Z normal)")
    print("  - Segment 2 (Frames 31..60):  Single Stance (Left foot locked, right foot raised in air)")
    print("  - Segment 3 (Frames 61..90):  Vault Touch (Foot on ground + Right hand on VaultBox top Z=1.05m)")
    print("  - Segment 4 (Frames 91..120): Foot on Wall (Foot on ground + Foot flat against VerticalWall Y=-4.0m)")
    print("  - Segment 5 (Frames 121..150): Ledge Hang (Bilateral hands grasp LedgeBar Z=1.95m, feet suspended)")
    print("  - Segment 6 (Frames 151..180): Flight Phase (Mid-air ballistic running stride, 0 contacts)")
    print("================================================================================")
    return blend_path


if __name__ == "__main__":
    generate_contact_model_prototype()
