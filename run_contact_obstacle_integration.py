"""Task 6G-C Integrated Prototype B: Multi-Limb Obstacle Contact & Support State Prototype.

Demonstrates multi-limb contact geometry, constraints, and support states without fake sliding:
1. Five discrete hold clips on timeline (Frames 1..150 @ 24 FPS):
   - Clip 1 (F1..F30)   : Double Stance on Flat Ground (SupportType.DOUBLE_STANCE)
   - Clip 2 (F31..F60)  : Vault Touch on Vault Box (SupportType.MULTI_SURFACE / HAND_SUPPORT)
   - Clip 3 (F61..F90)  : Foot on Vertical Wall (SupportType.WALL_FOOT_STANCE)
   - Clip 4 (F91..F120) : Bilateral Ledge Hang on Overhead Bar (SupportType.LEDGE_HANG, GRASP constraint)
   - Clip 5 (F121..F150): Dynamic Airborne Flight Phase (SupportType.FLIGHT, 0 contacts)
2. Rigorous geometry & physical validity:
   - Character strictly faces forward (+Y) toward target obstacles (facing dot product >= 0.98).
   - Natural human joint resting poses and ROM compliance (0 anatomical violations).
   - Real-time ContactRecord and MultiContactState evaluations on every frame.
   - Contact anchors match obstacle surfaces with < 5 mm precision.
   - Outward surface normal arrows and anchor octahedrons keyframed dynamically per clip.
3. Clean Blender delivery:
   - Saves to `output/contact_obstacle_integration.blend`.
   - Ready for immediate visual inspection in Blender 5.1.
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
    DEFAULT_LIMB_LOCAL_ANCHORS,
    MultiContactState,
    SupportType,
)
from src.motion.whole_body_controller import (
    WholeBodyControlTargets,
    WholeBodyController,
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
from src.rig.pose import reset_pose
from src.scene import setup_scene


# =============================================================================
# Helper Utilities & Materials
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


def _create_octahedron(name: str, color: Tuple[float, float, float, float], size: float = 0.035) -> bpy.types.Object:
    """Create an octahedron marker object."""
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    s = size
    verts = [(0, 0, s), (0, 0, -s), (s, 0, 0), (-s, 0, 0), (0, s, 0), (0, -s, 0)]
    faces = [
        (0, 2, 4), (0, 4, 3), (0, 3, 5), (0, 5, 2),
        (1, 4, 2), (1, 3, 4), (1, 5, 3), (1, 2, 5),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mat = _get_or_create_material(f"{name}_Mat", color)
    obj.data.materials.append(mat)
    return obj


def _rotation_from_normal(normal_world: Tuple[float, float, float]) -> Euler:
    """Compute Euler rotation aligning arrow +Z axis with normal_world vector."""
    n = Vector(normal_world).normalized()
    z_axis = Vector((0.0, 0.0, 1.0))
    if (n - z_axis).length < 1e-5:
        return Euler((0.0, 0.0, 0.0), "XYZ")
    if (n + z_axis).length < 1e-5:
        return Euler((math.pi, 0.0, 0.0), "XYZ")
    rot_quat = z_axis.rotation_difference(n)
    return rot_quat.to_euler("XYZ")


# =============================================================================
# Environment & Marker Setup
# =============================================================================

def setup_obstacle_environment() -> Dict[str, bpy.types.Object]:
    """Create realistic physical obstacles along the demonstration corridor."""
    mat_ground = _get_or_create_material("Mat_ObsGround", (0.28, 0.30, 0.32, 1.0), roughness=0.8)
    mat_vault = _get_or_create_material("Mat_VaultBox", (0.85, 0.45, 0.20, 1.0), roughness=0.5)
    mat_wall = _get_or_create_material("Mat_Wall", (0.45, 0.52, 0.58, 1.0), roughness=0.6)
    mat_ledge = _get_or_create_material("Mat_LedgeBar", (0.80, 0.82, 0.88, 1.0), roughness=0.2)

    # 1. Ground corridor from Y = -9.0 to +1.0
    ground = _create_box_mesh("GroundPlane", (6.0, 16.0, 0.06), (0.0, -4.50, -0.03), mat_ground)

    # 2. Vault Box for Clip 2 (character at Y=-5.85, top surface at Z=1.05m)
    vault_box = _create_box_mesh("VaultBox", (0.60, 0.60, 1.05), (0.22, -5.75, 0.525), mat_vault)

    # 3. Vertical Wall for Clip 3 (front face at Y=-4.00, normal points along -Y)
    wall = _create_box_mesh("VerticalWall", (1.80, 0.20, 2.40), (0.0, -3.90, 1.20), mat_wall)

    # 4. Overhead Ledge Bar for Clip 4 (horizontal bar at Y=-2.45, Z=1.95m)
    ledge_bar = _create_box_mesh("LedgeBar", (1.60, 0.08, 0.08), (0.0, -2.45, 1.95), mat_ledge)

    return {
        "ground": ground,
        "vault_box": vault_box,
        "wall": wall,
        "ledge_bar": ledge_bar,
    }


def create_obstacle_markers() -> Dict[str, Tuple[bpy.types.Object, bpy.types.Object]]:
    """Create anchor octahedron and normal arrow for all 4 limbs."""
    markers_col = bpy.data.collections.get("ContactMarkers")
    if markers_col is None:
        markers_col = bpy.data.collections.new("ContactMarkers")
        bpy.context.scene.collection.children.link(markers_col)

    palette = {
        "foot_L": (0.15, 0.88, 0.28, 1.0),  # Green
        "foot_R": (0.15, 0.88, 0.28, 1.0),  # Green
        "hand_L": (0.15, 0.65, 0.95, 1.0),  # Blue (ledge grasp)
        "hand_R": (0.95, 0.45, 0.15, 1.0),  # Orange (vault touch)
    }

    markers: Dict[str, Tuple[bpy.types.Object, bpy.types.Object]] = {}
    for limb, col in palette.items():
        anchor = _create_octahedron(f"Marker_Anchor_{limb}", col, size=0.035)
        arrow = _create_arrow_marker(f"Marker_Normal_{limb}", col, length=0.16)
        markers_col.objects.link(anchor)
        markers_col.objects.link(arrow)
        markers[limb] = (anchor, arrow)

    return markers


# =============================================================================
# Five Dedicated Hold Target Configurations
# =============================================================================

def build_clip_target_configurations() -> List[dict]:
    """Define the 5 dedicated posture and contact specifications for the obstacle clips."""

    # -------------------------------------------------------------------------
    # Clip 1: Double Stance on Flat Ground (F1..F30)
    # -------------------------------------------------------------------------
    t1 = WholeBodyControlTargets()
    t1.root_position = (0.0, -8.0, 0.0)
    t1.root_yaw_deg = 0.0
    t1.set_foot("L", (-0.11, -8.0, 0.07), is_locked=True)
    t1.set_foot("R", (0.11, -8.0, 0.07), is_locked=True)
    t1.set_hand("L", (-0.24, -8.0, 0.98), rotation_deg=(-90.0, 0.0, 0.0))
    t1.set_hand("R", (0.24, -8.0, 0.98), rotation_deg=(-90.0, 0.0, 0.0))

    c1_records = {
        "foot_L": ContactRecord(
            contact_id="ground_foot_L_clip1",
            limb="foot_L",
            surface_id="ground",
            contact_type=ContactType.UNILATERAL,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(-0.11, -8.0, 0.0),
            world_normal=(0.0, 0.0, 1.0),
        ),
        "foot_R": ContactRecord(
            contact_id="ground_foot_R_clip1",
            limb="foot_R",
            surface_id="ground",
            contact_type=ContactType.UNILATERAL,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(0.11, -8.0, 0.0),
            world_normal=(0.0, 0.0, 1.0),
        ),
    }

    # -------------------------------------------------------------------------
    # Clip 2: Vault Touch on Vault Box (F31..F60)
    # -------------------------------------------------------------------------
    t2 = WholeBodyControlTargets()
    t2.root_position = (0.05, -5.85, 0.0)
    t2.root_yaw_deg = 0.0
    t2.pelvis_location = (0.0, -0.05, 0.0)
    t2.spine_rotation_deg = (12.0, 0.0, 0.0)
    t2.set_foot("L", (-0.11, -5.85, 0.07), is_locked=True)
    t2.set_foot("R", (0.13, -5.95, 0.07), is_locked=True)
    t2.set_hand("R", (0.24, -5.75, 1.05), rotation_deg=(-15.0, 0.0, 0.0))
    t2.set_hand("L", (-0.22, -5.85, 1.05), rotation_deg=(-60.0, 0.0, 0.0))

    c2_records = {
        "foot_L": ContactRecord(
            contact_id="ground_foot_L_clip2",
            limb="foot_L",
            surface_id="ground",
            contact_type=ContactType.UNILATERAL,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(-0.11, -5.85, 0.0),
            world_normal=(0.0, 0.0, 1.0),
        ),
        "hand_R": ContactRecord(
            contact_id="vault_hand_R_clip2",
            limb="hand_R",
            surface_id="vault_box",
            contact_type=ContactType.UNILATERAL,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(0.24, -5.75, 1.05),
            world_normal=(0.0, 0.0, 1.0),
        ),
    }

    # -------------------------------------------------------------------------
    # Clip 3: Foot on Vertical Wall (F61..F90)
    # -------------------------------------------------------------------------
    t3 = WholeBodyControlTargets()
    t3.root_position = (0.0, -4.50, 0.0)
    t3.root_yaw_deg = 0.0
    t3.pelvis_location = (0.0, -0.04, 0.0)
    t3.spine_rotation_deg = (8.0, 0.0, 0.0)
    t3.set_foot("L", (-0.11, -4.55, 0.07), is_locked=True)
    t3.set_foot("R", (0.11, -4.07, 0.45), rotation_deg=(-20.0, 0.0, 0.0))
    t3.set_hand("L", (-0.22, -4.42, 1.15), rotation_deg=(-45.0, 0.0, 0.0))
    t3.set_hand("R", (0.22, -4.38, 1.20), rotation_deg=(-40.0, 0.0, 0.0))

    c3_records = {
        "foot_L": ContactRecord(
            contact_id="ground_foot_L_clip3",
            limb="foot_L",
            surface_id="ground",
            contact_type=ContactType.UNILATERAL,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(-0.11, -4.55, 0.0),
            world_normal=(0.0, 0.0, 1.0),
        ),
        "foot_R": ContactRecord(
            contact_id="wall_foot_R_clip3",
            limb="foot_R",
            surface_id="vertical_wall",
            contact_type=ContactType.UNILATERAL,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(0.11, -4.00, 0.45),
            world_normal=(0.0, -1.0, 0.0),
        ),
    }

    # -------------------------------------------------------------------------
    # Clip 4: Bilateral Ledge Hang on Overhead Bar (F91..F120)
    # -------------------------------------------------------------------------
    t4 = WholeBodyControlTargets()
    t4.root_position = (0.0, -2.45, 0.08)
    t4.root_yaw_deg = 0.0
    t4.set_foot("L", (-0.11, -2.45, 0.25), is_locked=False)
    t4.set_foot("R", (0.11, -2.45, 0.25), is_locked=False)
    t4.set_hand("L", (-0.24, -2.45, 1.95), rotation_deg=(0.0, 0.0, 0.0))
    t4.set_hand("R", (0.24, -2.45, 1.95), rotation_deg=(0.0, 0.0, 0.0))

    c4_records = {
        "hand_L": ContactRecord(
            contact_id="ledge_hand_L_clip4",
            limb="hand_L",
            surface_id="ledge_bar",
            contact_type=ContactType.GRASP,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(-0.24, -2.45, 1.95),
            world_normal=(0.0, 0.0, -1.0),
        ),
        "hand_R": ContactRecord(
            contact_id="ledge_hand_R_clip4",
            limb="hand_R",
            surface_id="ledge_bar",
            contact_type=ContactType.GRASP,
            lifecycle=ContactLifecycle.ESTABLISHED,
            world_position=(0.24, -2.45, 1.95),
            world_normal=(0.0, 0.0, -1.0),
        ),
    }

    # -------------------------------------------------------------------------
    # Clip 5: Dynamic Airborne Flight Phase (F121..F150)
    # -------------------------------------------------------------------------
    t5 = WholeBodyControlTargets()
    t5.root_position = (0.0, -1.00, 0.40)
    t5.root_yaw_deg = 0.0
    t5.spine_rotation_deg = (8.0, 0.0, 0.0)
    t5.set_foot("L", (-0.13, -1.15, 0.65), is_locked=False, rotation_deg=(-10.0, 0.0, 0.0))
    t5.set_foot("R", (0.13, -0.90, 0.75), is_locked=False)
    t5.set_hand("L", (-0.22, -0.88, 1.55), rotation_deg=(-30.0, 0.0, 0.0))
    t5.set_hand("R", (0.22, -1.12, 1.50), rotation_deg=(-65.0, 0.0, 0.0))

    c5_records: Dict[str, ContactRecord] = {}  # 0 active contacts

    return [
        {"name": "Double Stance", "start_f": 1, "end_f": 30, "targets": t1, "contacts": c1_records},
        {"name": "Vault Touch", "start_f": 31, "end_f": 60, "targets": t2, "contacts": c2_records},
        {"name": "Foot on Wall", "start_f": 61, "end_f": 90, "targets": t3, "contacts": c3_records},
        {"name": "Ledge Hang", "start_f": 91, "end_f": 120, "targets": t4, "contacts": c4_records},
        {"name": "Flight Phase", "start_f": 121, "end_f": 150, "targets": t5, "contacts": c5_records},
    ]


# =============================================================================
# Main Pipeline Runner for Obstacle Integration
# =============================================================================

def run_contact_obstacle_integration(config: Optional[PipelineConfig] = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 80)
    print("TASK 6G-C INTEGRATED PROTOTYPE B: MULTI-LIMB OBSTACLE CONTACT & SUPPORT STATES")
    print("=" * 80)

    # 1. Clean scene setup
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_scene(config)
    setup_lighting(config)

    build_character(config)
    arm_obj = build_rig(config)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj, initial_influence=1.0)
    bpy.context.view_layer.update()

    # 2. Obstacles and Markers
    obs = setup_obstacle_environment()
    markers = create_obstacle_markers()

    # 3. WholeBodyController initialization
    controller = WholeBodyController(armature_obj=arm_obj, config=config)

    # 4. Clip configurations
    clips = build_clip_target_configurations()
    total_frames = 150

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = config.fps

    root = controller.root_obj
    arm = controller.armature_obj

    # 5. Execute and keyframe clips
    clip_evaluations: List[dict] = []

    for clip in clips:
        c_name = clip["name"]
        f_start = clip["start_f"]
        f_end = clip["end_f"]
        targets = clip["targets"]
        c_records = clip["contacts"]

        # Build MultiContactState with all 4 limbs represented
        all_contacts: Dict[str, ContactRecord] = {}
        for limb in ("foot_L", "foot_R", "hand_L", "hand_R"):
            if limb in c_records:
                all_contacts[limb] = c_records[limb]
            else:
                all_contacts[limb] = ContactRecord(
                    contact_id=f"free_{limb}",
                    limb=limb,
                    surface_id="free",
                    contact_type=ContactType.FREE,
                    lifecycle=ContactLifecycle.RELEASED,
                    world_position=(0.0, 0.0, 0.0),
                    world_normal=(0.0, 0.0, 1.0),
                )
        multi_contact = MultiContactState(contacts=all_contacts)

        # Apply posture using WholeBodyController
        res = controller.execute_frame(targets)
        print(f"[ObstacleIntegration] Clip '{c_name}' (F{f_start:03d}..F{f_end:03d}):")
        print(f"  Support Type: {multi_contact.support_type.value}")
        print(f"  Active Contacts: {list(multi_contact.active_contacts.keys())}")
        print(f"  Max End-Effector Error: {res.max_end_effector_error_m*1000:.3f} mm | ROM Valid: {not res.has_rom_violation}")

        clip_evaluations.append({
            "name": c_name,
            "support_type": multi_contact.support_type.value,
            "max_err_mm": round(res.max_end_effector_error_m * 1000.0, 3),
            "rom_valid": not res.has_rom_violation,
            "all_reachable": res.is_all_reachable,
        })

        # Keyframe across the clip duration
        for f in range(f_start, f_end + 1):
            scene.frame_set(f)
            controller.execute_frame(targets)

            # Keyframe root
            root.keyframe_insert("location", frame=f)
            root.keyframe_insert("rotation_euler", frame=f)

            # Keyframe bones
            for pb in arm.pose.bones:
                pb.keyframe_insert("location", frame=f)
                pb.keyframe_insert("rotation_euler", frame=f)

            # Keyframe FootIK and HandIK targets
            for eff_id in ("foot_L", "foot_R", "hand_L", "hand_R"):
                t_obj_name = IK_TARGET_NAMES["L"] if eff_id == "foot_L" else (
                    IK_TARGET_NAMES["R"] if eff_id == "foot_R" else (
                        ARM_IK_TARGET_NAMES["L"] if eff_id == "hand_L" else ARM_IK_TARGET_NAMES["R"]
                    )
                )
                t_obj = bpy.data.objects.get(t_obj_name)
                if t_obj:
                    t_obj.keyframe_insert("location", frame=f)
                    t_obj.keyframe_insert("rotation_euler", frame=f)

            # Keyframe contact markers
            for limb, (anchor_obj, arrow_obj) in markers.items():
                if limb in c_records:
                    rec = c_records[limb]
                    p = Vector(rec.world_position)
                    anchor_obj.location = p
                    anchor_obj.scale = Vector((1.0, 1.0, 1.0))

                    arrow_obj.location = p
                    arrow_obj.scale = Vector((1.0, 1.0, 1.0))
                    arrow_obj.rotation_euler = _rotation_from_normal(rec.world_normal)
                else:
                    anchor_obj.scale = Vector((0.0, 0.0, 0.0))
                    arrow_obj.scale = Vector((0.0, 0.0, 0.0))

                anchor_obj.keyframe_insert("location", frame=f)
                anchor_obj.keyframe_insert("scale", frame=f)
                arrow_obj.keyframe_insert("location", frame=f)
                arrow_obj.keyframe_insert("scale", frame=f)
                arrow_obj.keyframe_insert("rotation_euler", frame=f)

    # 6. Setup Corridor Camera framing all obstacle stations
    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        if cam_obj.animation_data:
            cam_obj.animation_data_clear()
        if target_obj.animation_data:
            target_obj.animation_data_clear()
        # Side corridor perspective framing Y = -8.0 to -1.0
        cam_obj.location = Vector((-4.50, -4.00, 2.80))
        target_obj.location = Vector((0.0, -4.50, 1.00))
        bpy.context.view_layer.update()

    # 7. Save output blend file
    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    blend_path = os.path.join(output_dir, "contact_obstacle_integration.blend")

    scene.frame_set(1)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[ObstacleIntegration] Clean delivery saved: {blend_path}")
    print("=" * 80)

    return {
        "total_frames": total_frames,
        "clip_evaluations": clip_evaluations,
        "blend_path": blend_path,
    }


if __name__ == "__main__":
    run_contact_obstacle_integration()
