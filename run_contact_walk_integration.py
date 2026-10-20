"""Task 6G-C Integrated Prototype A: Procedural Continuous Walking with Dynamic Contact Model.

Demonstrates full engineering-grade integration:
1. True historical procedural locomotion (Task 5C / 6A start-accelerate-steady-decelerate-stop):
   - 204 frames (8.5s @ 24 FPS) continuous locomotion along +Y corridor.
   - Alternating left and right leg stance/swing phases across 7 coordinated half-steps.
   - Natural pelvic vertical oscillation (crouch/rise), torso forward pitch, and contralateral arm swing.
   - Stance foot locked via foot_contact with < 0.05 mm drift.
   - Swing foot follows smooth sine/cosine lift trajectory (step height ~ 0.04m).
2. Dynamic ContactModel evaluation & telemetry:
   - On every frame, evaluates MultiContactState for foot_L and foot_R.
   - In stance phase: lifecycle = ESTABLISHED, type = UNILATERAL, normal = (0, 0, 1).
     Anchor marker (green octahedron) and normal arrow are keyframed active on ground at foot contact location.
   - In swing phase: lifecycle = RELEASED, type = FREE.
     Markers are scaled to 0 (invisible).
   - SupportType dynamically transitions: DOUBLE_STANCE -> SINGLE_STANCE_L -> SINGLE_STANCE_R ... -> DOUBLE_STANCE.
3. Clean Blender delivery:
   - Saves directly to `output/contact_walk_integration.blend`.
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

from src.character.builder import character_start_location
from src.config import PipelineConfig
from src.motion.contact_model import (
    ContactLifecycle,
    ContactRecord,
    ContactType,
    MultiContactState,
    SupportType,
)
from src.motion.forward_walk_prototype import _ensure_scene_with_ik_rig
from src.motion.start_stop_walk import generate_start_stop_walk
from src.render import configure_render


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


# =============================================================================
# Main Pipeline Runner for Walk Integration
# =============================================================================

def run_contact_walk_integration(config: Optional[PipelineConfig] = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 80)
    print("TASK 6G-C INTEGRATED PROTOTYPE A: CONTINUOUS WALKING + DYNAMIC CONTACT MODEL")
    print("=" * 80)

    # 1. Setup clean scene with character rig and IK
    arm_obj = _ensure_scene_with_ik_rig(config)

    # 2. Add ground reference plane with grid material for foot contact clarity
    ground_mat = _get_or_create_material("Mat_WalkGround", (0.25, 0.27, 0.29, 1.0), roughness=0.8)
    ground_mesh = bpy.data.meshes.new("WalkGround_Mesh")
    ground_obj = bpy.data.objects.new("WalkGround", ground_mesh)
    bpy.context.scene.collection.objects.link(ground_obj)

    # Ground box from Y = -9.0 to -5.0
    gx, gy, gz = 2.0, 5.0, 0.04
    verts = [
        (-gx, -gy, -gz), (gx, -gy, -gz), (gx, gy, -gz), (-gx, gy, -gz),
        (-gx, -gy, 0.0), (gx, -gy, 0.0), (gx, gy, 0.0), (-gx, gy, 0.0),
    ]
    faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5),
    ]
    ground_mesh.from_pydata(verts, [], faces)
    ground_mesh.update()
    ground_obj.location = Vector((0.0, -7.0, 0.0))
    ground_obj.data.materials.append(ground_mat)

    # 3. Create visual contact markers
    markers_col = bpy.data.collections.get("ContactMarkers")
    if markers_col is None:
        markers_col = bpy.data.collections.new("ContactMarkers")
        bpy.context.scene.collection.children.link(markers_col)

    green_color = (0.15, 0.88, 0.28, 1.0)
    anchor_L = _create_octahedron("Marker_Anchor_foot_L", green_color, size=0.030)
    arrow_L = _create_arrow_marker("Marker_Normal_foot_L", green_color, length=0.15)
    anchor_R = _create_octahedron("Marker_Anchor_foot_R", green_color, size=0.030)
    arrow_R = _create_arrow_marker("Marker_Normal_foot_R", green_color, length=0.15)

    for m_obj in (anchor_L, arrow_L, anchor_R, arrow_R):
        markers_col.objects.link(m_obj)

    # 4. Generate the true 204-frame locomotion sequence using validated generator
    walk_data = generate_start_stop_walk(config, arm_obj)
    records = walk_data["frame_records"]
    total_frames = walk_data["total_frames"]

    print(f"[WalkIntegration] Generated {total_frames} frames of verified locomotion.")
    print(f"  Total Root Displacement: {walk_data['total_root_displacement']:.4f} m (+Y)")
    print(f"  Peak Speed             : {walk_data['peak_speed_mps']:.4f} m/s")

    # 5. Evaluate ContactModel telemetry and keyframe markers for every frame
    contact_states_by_frame: List[MultiContactState] = []
    support_type_counts: Dict[str, int] = {}

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total_frames

    for frame in range(1, total_frames + 1):
        scene.frame_set(frame)
        rec = records[frame - 1]
        sl = rec["state_l"]
        sr = rec["state_r"]
        phase_l = rec["phase_l"]
        phase_r = rec["phase_r"]

        # Left foot contact
        is_l_stance = (phase_l == "stance")
        pos_l = sl["contact_world"] if is_l_stance else sl["foot_head_world"]
        rec_l = ContactRecord(
            contact_id=f"ground_foot_L_{frame:03d}",
            limb="foot_L",
            surface_id="ground",
            contact_type=ContactType.UNILATERAL if is_l_stance else ContactType.FREE,
            lifecycle=ContactLifecycle.ESTABLISHED if is_l_stance else ContactLifecycle.RELEASED,
            world_position=(pos_l[0], pos_l[1], 0.0 if is_l_stance else sl["foot_min_z"]),
            world_normal=(0.0, 0.0, 1.0),
        )

        # Right foot contact
        is_r_stance = (phase_r == "stance")
        pos_r = sr["contact_world"] if is_r_stance else sr["foot_head_world"]
        rec_r = ContactRecord(
            contact_id=f"ground_foot_R_{frame:03d}",
            limb="foot_R",
            surface_id="ground",
            contact_type=ContactType.UNILATERAL if is_r_stance else ContactType.FREE,
            lifecycle=ContactLifecycle.ESTABLISHED if is_r_stance else ContactLifecycle.RELEASED,
            world_position=(pos_r[0], pos_r[1], 0.0 if is_r_stance else sr["foot_min_z"]),
            world_normal=(0.0, 0.0, 1.0),
        )

        multi_contact = MultiContactState(contacts={"foot_L": rec_l, "foot_R": rec_r})
        contact_states_by_frame.append(multi_contact)
        st_name = multi_contact.support_type.value
        support_type_counts[st_name] = support_type_counts.get(st_name, 0) + 1

        # Keyframe visual markers:
        # Left foot marker
        if is_l_stance:
            anchor_L.location = Vector((pos_l[0], pos_l[1], 0.0))
            anchor_L.scale = Vector((1.0, 1.0, 1.0))
            arrow_L.location = Vector((pos_l[0], pos_l[1], 0.0))
            arrow_L.scale = Vector((1.0, 1.0, 1.0))
            arrow_L.rotation_euler = Euler((0.0, 0.0, 0.0))
        else:
            anchor_L.scale = Vector((0.0, 0.0, 0.0))
            arrow_L.scale = Vector((0.0, 0.0, 0.0))

        anchor_L.keyframe_insert("location", frame=frame)
        anchor_L.keyframe_insert("scale", frame=frame)
        arrow_L.keyframe_insert("location", frame=frame)
        arrow_L.keyframe_insert("scale", frame=frame)
        arrow_L.keyframe_insert("rotation_euler", frame=frame)

        # Right foot marker
        if is_r_stance:
            anchor_R.location = Vector((pos_r[0], pos_r[1], 0.0))
            anchor_R.scale = Vector((1.0, 1.0, 1.0))
            arrow_R.location = Vector((pos_r[0], pos_r[1], 0.0))
            arrow_R.scale = Vector((1.0, 1.0, 1.0))
            arrow_R.rotation_euler = Euler((0.0, 0.0, 0.0))
        else:
            anchor_R.scale = Vector((0.0, 0.0, 0.0))
            arrow_R.scale = Vector((0.0, 0.0, 0.0))

        anchor_R.keyframe_insert("location", frame=frame)
        anchor_R.keyframe_insert("scale", frame=frame)
        arrow_R.keyframe_insert("location", frame=frame)
        arrow_R.keyframe_insert("scale", frame=frame)
        arrow_R.keyframe_insert("rotation_euler", frame=frame)

    print(f"[WalkIntegration] Support states across {total_frames} frames:")
    for st_name, count in sorted(support_type_counts.items()):
        print(f"  - {st_name:18s}: {count:3d} frames ({count/total_frames*100:.1f}%)")

    # 6. Set Camera to frame the walking corridor cleanly
    start_x, start_y, _ = character_start_location(config)
    configure_render(config)
    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        if cam_obj.animation_data:
            cam_obj.animation_data_clear()
        if target_obj.animation_data:
            target_obj.animation_data_clear()
        # Diagonal side view framing the Y=-8.0 to -6.5 path
        cam_obj.location = Vector((start_x - 3.20, start_y + 4.50, 1.60))
        target_obj.location = Vector((start_x, start_y + 0.65, 0.88))
        bpy.context.view_layer.update()

    # 7. Save output blend file
    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)
    blend_path = os.path.join(output_dir, "contact_walk_integration.blend")

    scene.frame_set(1)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[WalkIntegration] Clean delivery saved: {blend_path}")
    print("=" * 80)

    return {
        "total_frames": total_frames,
        "total_root_displacement": walk_data["total_root_displacement"],
        "peak_speed_mps": walk_data["peak_speed_mps"],
        "support_type_counts": support_type_counts,
        "blend_path": blend_path,
    }


if __name__ == "__main__":
    run_contact_walk_integration()
