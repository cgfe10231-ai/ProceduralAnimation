"""Procedural continuous forward walking generator (Task 5B).

Extends the Task 5A 48-frame gait cycle to 3 continuous forward cycles (144 frames,
6.0s @ 24 FPS) synchronized with root translation along the scene's +Y corridor axis.

Key Properties:
- Reuses Task 4C two-bone leg IK (`FootIK.L/R`, `KneePole.L/R`), Task 4D support-foot
  locking (`lock_foot_contact`, `unlock_foot_contact`, `evaluate_foot_support`,
  `move_character_root_with_support`), and Task 5A upper-body/arm coordination.
- Synchronizes `CharacterRoot` forward speed (`v = stride_length / cycle_duration = 0.24 m/s`)
  with alternating 24-frame stance and swing phases (`step_length = 0.24 m` per half-cycle,
  `stride_length = 0.48 m` per 48-frame cycle).
- During each 24-frame stance phase, the support foot remains locked at a fixed world
  coordinate `Y_stance(k) = start_y + (k + 0.5) * step_length` while `CharacterRoot`
  advances smoothly over it.
- During each 24-frame swing phase, the swing foot unlocks from its previous stance point
  `Y_stance(k - 1)` and follows a C1-continuous arc to land at its new forward target
  `Y_stance(k + 1) = Y_stance(k - 1) + 2 * step_length`.
"""

import math
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

from src.character.builder import character_start_location
from src.config import PipelineConfig
from src.motion.walk_cycle import _clear_existing_animation_data, _keyframe_walk_frame
from src.rig.foot_contact import (
    evaluate_foot_support,
    lock_foot_contact,
    move_character_root_with_support,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    _resolve_armature,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose, set_bone_location, set_bone_rotation


def compute_forward_swing_point(
    y_start: float,
    y_end: float,
    swing_s: float,
    step_height: float,
) -> Tuple[float, float]:
    """Compute (world_y, z_lift) for a foot swinging forward from `y_start` to `y_end`
    over normalized half-step progress `swing_s` in [0, 1].
    """
    s = max(0.0, min(1.0, swing_s))
    alpha = 0.5 * (1.0 - math.cos(math.pi * s))
    world_y = y_start + alpha * (y_end - y_start)
    z_lift = step_height * (math.sin(math.pi * s) ** 2)
    return world_y, z_lift


def _apply_upper_body_and_pelvis_gait_pose(
    arm: bpy.types.Object,
    config: PipelineConfig,
    u: float,
) -> Tuple[float, float]:
    """Apply pelvis bob/sway/rotation, spine counter-rotation, head stabilization,
    and contra-lateral arm swing for normalized full-cycle phase `u` in [0, 1).
    """
    theta = 2.0 * math.pi * u
    sin_t = math.sin(theta)
    cos_2t = math.cos(2.0 * theta)

    # Pelvis local axes: +X = World +X, +Y = World +Z (vertical), +Z = World -Y
    pelvis_dx = -config.walk_pelvis_sway_amp * sin_t
    pelvis_dz = config.forward_walk_pelvis_crouch - config.walk_pelvis_bob_amp * cos_2t
    set_bone_location(arm, "pelvis", (pelvis_dx, pelvis_dz, 0.0), update=False)

    pelvis_rx = -1.5 + 1.0 * cos_2t
    pelvis_ry = config.walk_pelvis_yaw_deg * sin_t
    pelvis_rz = config.walk_pelvis_roll_deg * sin_t
    set_bone_rotation(arm, "pelvis", (pelvis_rx, pelvis_ry, pelvis_rz), update=False)

    spine_rx = -config.walk_torso_lean_deg - 0.8 * cos_2t
    spine_ry = -config.walk_torso_yaw_deg * sin_t
    spine_rz = -0.6 * pelvis_rz
    set_bone_rotation(arm, "spine", (spine_rx, spine_ry, spine_rz), update=False)

    total_rx = pelvis_rx + spine_rx
    total_ry = pelvis_ry + spine_ry
    total_rz = pelvis_rz + spine_rz
    set_bone_rotation(
        arm,
        "neck",
        (-0.45 * total_rx, -0.45 * total_ry, -0.45 * total_rz),
        update=False,
    )
    set_bone_rotation(
        arm,
        "head",
        (-0.45 * total_rx, -0.45 * total_ry, -0.45 * total_rz),
        update=False,
    )

    arm_l_rx = config.walk_arm_swing_deg * sin_t
    arm_r_rx = -config.walk_arm_swing_deg * sin_t
    elbow_l_rx = config.walk_elbow_base_deg + config.walk_elbow_swing_deg * max(0.0, sin_t)
    elbow_r_rx = config.walk_elbow_base_deg + config.walk_elbow_swing_deg * max(0.0, -sin_t)

    set_bone_rotation(arm, "upper_arm.L", (arm_l_rx, 0.0, -4.0), update=False)
    set_bone_rotation(arm, "forearm.L", (elbow_l_rx, 0.0, 0.0), update=False)
    set_bone_rotation(arm, "upper_arm.R", (arm_r_rx, 0.0, 4.0), update=False)
    set_bone_rotation(arm, "forearm.R", (elbow_r_rx, 0.0, 0.0), update=True)

    return arm_l_rx, arm_r_rx


def generate_forward_walk(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
) -> dict:
    """Generate and keyframe 3 continuous forward walk cycles (144 frames @ 24 FPS)."""
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    if root_obj is None:
        raise RuntimeError("CharacterRoot object not found")

    scene = bpy.context.scene
    cycle_frames = config.walk_cycle_frames
    half_cycle = cycle_frames // 2
    total_frames = config.forward_walk_frames
    step_len = config.forward_walk_step_length
    step_height = config.forward_walk_step_height

    scene.render.fps = config.fps
    scene.frame_start = 1
    scene.frame_end = total_frames

    start_x, start_y, start_z = character_start_location(config)
    root_obj.location = Vector((start_x, start_y, start_z))
    root_obj.rotation_euler = (0.0, 0.0, 0.0)

    reset_pose(arm)
    setup_leg_ik(arm)
    reset_leg_ik(arm)
    _clear_existing_animation_data(arm)

    frame_records: List[dict] = []
    unreachable_events: List[dict] = []

    for frame in range(1, total_frames + 1):
        scene.frame_set(frame)
        tau = frame - 1
        k = tau // half_cycle  # Half-step index: 0..5 across 144 frames
        s = (tau - k * half_cycle) / float(half_cycle)  # Progress [0, 23/24] within half-step k
        u = (tau % cycle_frames) / float(cycle_frames)  # Full-cycle phase [0, 47/48]

        # Synchronized continuous forward root position along +Y
        root_y = start_y + (tau / float(half_cycle)) * step_len
        root_world = (start_x, root_y, start_z)

        # Move root while preserving any active support locks
        move_character_root_with_support(arm, root_world)
        arm_l_rx, arm_r_rx = _apply_upper_body_and_pelvis_gait_pose(arm, config, u)

        # Stance target for half-step k and swing start/end targets
        y_stance_k = start_y + (k + 0.5) * step_len
        y_swing_start = start_y + (k - 0.5) * step_len
        y_swing_end = start_y + (k + 1.5) * step_len
        y_swing, z_lift = compute_forward_swing_point(
            y_swing_start, y_swing_end, s, step_height
        )

        if k % 2 == 0:
            # Even half-step (k = 0, 2, 4): Left Foot in Stance, Right Foot in Swing
            if tau % half_cycle == 0:
                state_l = lock_foot_contact(
                    arm,
                    "L",
                    contact_world_xyz=(start_x - HIP_X_OFFSET, y_stance_k, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
            else:
                state_l = evaluate_foot_support(arm, "L")

            unlock_foot_contact(arm, "R", reparent_to_root=False)
            set_foot_ik_target(
                arm,
                "R",
                (start_x + HIP_X_OFFSET, y_swing, start_z + ANKLE_REST_Z + z_lift),
                foot_rotation_deg=(0.0, 0.0, 0.0),
            )
            state_r = evaluate_foot_support(arm, "R")
            phase_l, phase_r = "stance", "swing"
        else:
            # Odd half-step (k = 1, 3, 5): Right Foot in Stance, Left Foot in Swing
            if tau % half_cycle == 0:
                state_r = lock_foot_contact(
                    arm,
                    "R",
                    contact_world_xyz=(start_x + HIP_X_OFFSET, y_stance_k, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
            else:
                state_r = evaluate_foot_support(arm, "R")

            unlock_foot_contact(arm, "L", reparent_to_root=False)
            set_foot_ik_target(
                arm,
                "L",
                (start_x - HIP_X_OFFSET, y_swing, start_z + ANKLE_REST_Z + z_lift),
                foot_rotation_deg=(0.0, 0.0, 0.0),
            )
            state_l = evaluate_foot_support(arm, "L")
            phase_l, phase_r = "swing", "stance"

        if not state_l["is_reachable"] or not state_l["strictly_in_reach"]:
            unreachable_events.append({
                "frame": frame,
                "side": "L",
                "phase": phase_l,
                "dist": round(state_l["hip_to_target_dist"], 5),
            })
        if not state_r["is_reachable"] or not state_r["strictly_in_reach"]:
            unreachable_events.append({
                "frame": frame,
                "side": "R",
                "phase": phase_r,
                "dist": round(state_r["hip_to_target_dist"], 5),
            })

        _keyframe_walk_frame(arm, root_obj, frame)

        frame_records.append({
            "frame": frame,
            "half_step_k": k,
            "u": round(u, 4),
            "root_y": round(root_y, 5),
            "phase_l": phase_l,
            "phase_r": phase_r,
            "state_l": state_l,
            "state_r": state_r,
            "arm_l_rx": round(arm_l_rx, 2),
            "arm_r_rx": round(arm_r_rx, 2),
        })

    if unreachable_events:
        raise RuntimeError(
            f"Encountered {len(unreachable_events)} IK reach violations during forward walk: "
            f"{unreachable_events[:5]}"
        )

    total_disp = frame_records[-1]["root_y"] - frame_records[0]["root_y"]
    elapsed_sec = (total_frames - 1) / float(config.fps)
    avg_speed = total_disp / elapsed_sec if elapsed_sec > 0 else 0.0

    print(
        f"[FORWARD_WALK] Keyframed {total_frames} frames ({config.forward_walk_cycles} cycles @ {config.fps} FPS): "
        f"root Y {frame_records[0]['root_y']:.3f}m -> {frame_records[-1]['root_y']:.3f}m "
        f"(disp={total_disp:.4f}m, speed={avg_speed:.4f}m/s), unreachable_events=0"
    )
    return {
        "total_frames": total_frames,
        "fps": config.fps,
        "total_root_displacement": total_disp,
        "average_speed_mps": avg_speed,
        "unreachable_count": len(unreachable_events),
        "frame_records": frame_records,
    }
