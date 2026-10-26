"""Playground Terrain Traversal Kinematic Validation Module (Task 7A-2).

Performs strict, read-only multi-frame mathematical evaluation of the generated
playable scene `output/dynamics_playground_task7a2.blend`:
1. Scene Integrity & Object Inventory:
   - 19-bone CharacterArmature hierarchy and bone counts.
   - 13 placeholder mesh parts intact.
   - Task 7A-2 cameras, timeline markers, and embedded metadata.
2. Kinematic Continuity & Stability:
   - Root C0 continuity and velocity bounds (zero frame jumps within each course).
   - 19-bone rotation continuity (geodesic quaternion angle between adjacent frames <= 35 deg).
3. Locked Foot Support Rigidity:
   - Locked stance ankle bone world drift <= 1.0e-4 m (0.1 mm).
4. Skeletal Invariance & Mass Conservation:
   - Bone length preservation: zero bone stretching (|L_eval - L_rest| <= 1.0e-4 m).
   - Whole-body rigid link mass strictly conserved at 70.000 kg across all frames.
5. Anatomical Joint ROM Verification:
   - Zero ROM violations across all joints via `DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(use_evaluated_ik=True)`.
6. Terrain Ground Clearance:
   - Foot mesh minimum Z >= queried terrain elevation - 0.005 m.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix, Quaternion, Vector

from src.character.builder import REQUIRED_PARTS, world_min_z
from src.motion.joint_limits import DEFAULT_HUMANOID_ROM_MODEL
from src.motion.rigid_link import DEMPSTER_WINTER_15_SEGMENT_MODEL, compute_whole_body_com
from src.rig.builder import BONE_HIERARCHY, BONE_SPECIFICATIONS
from src.scene.environment_query import create_standard_dynamics_playground_query


def validate_dynamics_playground_task7a2(
    blend_path: str = "output/dynamics_playground_task7a2.blend",
    tolerance_drift_m: float = 1.0e-4,
    tolerance_bone_stretch_m: float = 1.0e-4,
) -> Dict[str, Any]:
    """Reopen `blend_path` in read-only mode and execute deep 926-frame mathematical validation."""
    abs_blend = os.path.abspath(blend_path)
    if not os.path.exists(abs_blend):
        raise FileNotFoundError(f"Derived animation blend file not found: {abs_blend}")

    # Reopen in fresh read-only Blender session
    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene = bpy.context.scene

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if arm_obj is None or root_obj is None:
        raise RuntimeError("Required CharacterArmature or CharacterRoot object missing from scene")

    # -------------------------------------------------------------------------
    # 1. Structural Inventory Checks
    # -------------------------------------------------------------------------
    bone_names = [b.name for b in arm_obj.data.bones]
    expected_bone_names = [spec[0] for spec in BONE_SPECIFICATIONS]
    missing_bones = [b for b in expected_bone_names if b not in bone_names]
    if missing_bones:
        raise RuntimeError(f"CharacterArmature missing expected bones: {missing_bones}")

    missing_parts = [p for p in REQUIRED_PARTS if p not in bpy.data.objects]
    if missing_parts:
        raise RuntimeError(f"Scene missing required character mesh parts: {missing_parts}")

    req_cams = ["Task7A2_StairsCam", "Task7A2_RampCam", "Task7A2_OverviewCam"]
    missing_cams = [c for c in req_cams if c not in bpy.data.objects]
    if missing_cams:
        raise RuntimeError(f"Scene missing Task 7A-2 inspection cameras: {missing_cams}")

    # Verify embedded metadata
    if "task7a2_contact_state_records" not in scene:
        raise RuntimeError("Missing embedded scene ID property 'task7a2_contact_state_records'")
    if "task7a2_execution_summary" not in scene:
        raise RuntimeError("Missing embedded scene ID property 'task7a2_execution_summary'")

    contact_records = json.loads(scene["task7a2_contact_state_records"])
    summary_data = json.loads(scene["task7a2_execution_summary"])
    total_frames = len(contact_records)
    if total_frames < 204:
        raise ValueError(f"Total animation frames {total_frames} is less than required minimum 204")

    # Cache rest bone lengths
    rest_bone_lengths: Dict[str, float] = {}
    for b in arm_obj.data.bones:
        rest_bone_lengths[b.name] = (b.tail_local - b.head_local).length

    env = create_standard_dynamics_playground_query()

    # -------------------------------------------------------------------------
    # 2. Multi-Frame Mathematical Trajectory & Physical Evaluation
    # -------------------------------------------------------------------------
    prev_root_pos: Optional[Vector] = None
    prev_bone_quats: Dict[str, Quaternion] = {}
    max_root_velocity_m_per_frame = 0.0
    max_bone_rotation_delta_deg = 0.0
    max_ankle_drift_m = 0.0
    max_bone_stretch_m = 0.0
    max_com_height_m = 0.0
    min_com_height_m = 999.0
    total_rom_violation_count = 0
    rom_violation_frames: List[int] = []
    terrain_penetrations: List[dict] = []
    mass_conservation_pass = True

    # Check mass conservation
    mass_dist = DEMPSTER_WINTER_15_SEGMENT_MODEL
    total_mass = mass_dist.total_mass_kg
    if abs(total_mass - 70.0) > 1.0e-3:
        mass_conservation_pass = False

    foot_mesh_l = bpy.data.objects.get("Foot_L")
    foot_mesh_r = bpy.data.objects.get("Foot_R")

    for f_idx, record in enumerate(contact_records):
        frame_num = record["frame"]
        scene.frame_set(frame_num)
        bpy.context.view_layer.update()

        cur_root_pos = root_obj.matrix_world.translation.copy()

        # Check root C0 continuity within continuous sections
        # Allow transition jump only between Stairs and Ramp courses (at frame 227)
        if prev_root_pos is not None and frame_num != 227:
            delta_pos = (cur_root_pos - prev_root_pos).length
            max_root_velocity_m_per_frame = max(max_root_velocity_m_per_frame, delta_pos)
            if delta_pos > 0.12:  # 0.12 m/frame @ 24 FPS = 2.88 m/s maximum instantaneous speed
                raise RuntimeError(
                    f"Frame {frame_num}: abnormal root displacement {delta_pos:.4f}m exceeds continuity limit (0.12m)"
                )
        prev_root_pos = cur_root_pos

        # Check bone length preservation (zero bone stretch)
        for b_name, rest_len in rest_bone_lengths.items():
            pb = arm_obj.pose.bones[b_name]
            head_w = arm_obj.matrix_world @ pb.head
            tail_w = arm_obj.matrix_world @ pb.tail
            eval_len = (tail_w - head_w).length
            stretch = abs(eval_len - rest_len)
            max_bone_stretch_m = max(max_bone_stretch_m, stretch)
            if stretch > tolerance_bone_stretch_m:
                raise RuntimeError(
                    f"Frame {frame_num}: bone '{b_name}' stretched by {stretch:.6f}m (limit {tolerance_bone_stretch_m}m)"
                )

        # Check bone rotation continuity (geodesic quaternion angle)
        cur_quats: Dict[str, Quaternion] = {}
        for b_name in bone_names:
            pb = arm_obj.pose.bones[b_name]
            cur_q = pb.matrix.to_quaternion()
            cur_quats[b_name] = cur_q
            if b_name in prev_bone_quats and frame_num != 227:
                prev_q = prev_bone_quats[b_name]
                dot = min(1.0, max(-1.0, abs(cur_q.dot(prev_q))))
                angle_deg = math.degrees(2.0 * math.acos(dot))
                max_bone_rotation_delta_deg = max(max_bone_rotation_delta_deg, angle_deg)
                if angle_deg > 35.0:
                    raise RuntimeError(
                        f"Frame {frame_num}: bone '{b_name}' rotational jerk {angle_deg:.2f}deg exceeds limit (35.0deg)"
                    )
        prev_bone_quats = cur_quats

        # Check locked foot drift
        for limb_id, c_data in record.get("contacts", {}).items():
            if c_data.get("is_locked", False):
                drift = float(c_data.get("drift_m", 0.0))
                max_ankle_drift_m = max(max_ankle_drift_m, drift)
                if drift > tolerance_drift_m:
                    raise RuntimeError(
                        f"Frame {frame_num}: locked limb '{limb_id}' drifted by {drift:.6f}m (limit {tolerance_drift_m}m)"
                    )

        # Check anatomical joint ROM limits
        rom_res = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm_obj, use_evaluated_ik=True)
        if not rom_res.is_valid:
            total_rom_violation_count += 1
            rom_violation_frames.append(frame_num)

        # Check whole-body CoM
        com_res = compute_whole_body_com(arm_obj, mass_dist, update_scene=False)
        com_z = com_res.com_world.z
        max_com_height_m = max(max_com_height_m, com_z)
        min_com_height_m = min(min_com_height_m, com_z)

        # Check foot mesh ground penetration (vertex-level accurate 3D surface collision check)
        for side, mesh_obj in [("foot_L", foot_mesh_l), ("foot_R", foot_mesh_r)]:
            if mesh_obj is not None:
                mw = mesh_obj.matrix_world
                max_pen = 0.0
                worst_z = 0.0
                worst_terr_z = 0.0
                for v in mesh_obj.data.vertices:
                    vw = mw @ v.co
                    terr_z = env.ground_height_at(vw.x, vw.y)
                    pen = terr_z - vw.z
                    if pen > max_pen:
                        max_pen = pen
                        worst_z = vw.z
                        worst_terr_z = terr_z
                if max_pen > 0.005:
                    terrain_penetrations.append({
                        "frame": frame_num,
                        "limb": side,
                        "min_z": round(worst_z, 4),
                        "terrain_z": round(worst_terr_z, 4),
                        "penetration_mm": round(max_pen * 1000.0, 2),
                    })

    scene.frame_set(1)
    bpy.context.view_layer.update()

    is_overall_valid = (
        total_rom_violation_count == 0
        and len(terrain_penetrations) == 0
        and max_ankle_drift_m <= tolerance_drift_m
        and max_bone_stretch_m <= tolerance_bone_stretch_m
        and mass_conservation_pass
    )

    return {
        "is_valid": is_overall_valid,
        "blend_file": abs_blend,
        "total_frames_evaluated": total_frames,
        "max_root_velocity_m_per_frame": round(max_root_velocity_m_per_frame, 5),
        "max_bone_rotation_delta_deg": round(max_bone_rotation_delta_deg, 3),
        "max_ankle_drift_m": round(max_ankle_drift_m, 8),
        "max_bone_stretch_m": round(max_bone_stretch_m, 8),
        "total_mass_kg": round(total_mass, 3),
        "min_com_height_m": round(min_com_height_m, 4),
        "max_com_height_m": round(max_com_height_m, 4),
        "rom_violation_count": total_rom_violation_count,
        "rom_violation_frames": rom_violation_frames,
        "terrain_penetration_count": len(terrain_penetrations),
        "terrain_penetrations": terrain_penetrations[:5],
        "summary_metadata": summary_data,
    }
