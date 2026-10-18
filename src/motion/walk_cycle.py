"""Procedural in-place humanoid walk cycle generator (Task 5A).

Generates a 48-frame (2.0s @ 24 FPS) seamless in-place walk cycle on the 19-bone
CharacterArmature using existing Task 4C two-bone leg IK (`FootIK.L/R`, `KneePole.L/R`)
and Task 4D support-foot locking (`lock_foot_contact`, `unlock_foot_contact`,
`evaluate_foot_support`).

Coordinate & Gait Conventions:
- World: Z-up, ground top at Z=0.0m, CharacterRoot fixed at (0.0, -8.0, 0.0), forward = +Y.
- Half-cycle 1 (frames 1..25, u in [0.0, 0.5]):
  - Left foot (`L`) is in Stance Phase (locked on ground at (-0.11, -8.0, 0.0)).
  - Right foot (`R`) is in Swing Phase (frames 2..24), lifting in +Z and stepping forward in +Y.
- Half-cycle 2 (frames 25..48, u in [0.5, 1.0)):
  - Right foot (`R`) is in Stance Phase (locked on ground at (+0.11, -8.0, 0.0)).
  - Left foot (`L`) is in Swing Phase (frames 26..48), lifting in +Z and stepping forward in +Y.
- Arms (`upper_arm.L/R`, `forearm.L/R`) swing contra-laterally to the legs.
- Pelvis exhibits realistic vertical bobbing (2x frequency), lateral weight shift toward the
  active stance leg, and subtle axial twist counter-balanced by the spine and stabilized head.
"""

import math
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

from src.character.builder import character_start_location, world_min_z
from src.config import PipelineConfig
from src.rig.foot_contact import (
    evaluate_foot_support,
    lock_foot_contact,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    IK_TARGET_NAMES,
    POLE_TARGET_NAMES,
    _resolve_armature,
    get_leg_ik_state,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose, set_bone_location, set_bone_rotation


def compute_swing_trajectory(
    swing_s: float,
    step_length: float,
    step_height: float,
) -> Tuple[float, float]:
    """Return (y_forward_offset, z_vertical_lift) for normalized swing phase s in [0, 1].

    Uses C1-continuous sin^2(pi * s) profiles so both position and velocity are zero
    at lift-off (s=0) and touch-down (s=1), ensuring seamless stance-swing transitions.
    """
    s = max(0.0, min(1.0, swing_s))
    envelope = math.sin(math.pi * s) ** 2
    z_lift = step_height * envelope
    # Asymmetric forward reach peaking slightly past mid-swing before landing smoothly
    y_offset = step_length * envelope * (0.75 + 0.25 * s)
    return y_offset, z_lift


def _clear_existing_animation_data(arm_obj: bpy.types.Object) -> None:
    """Clear previous actions on CharacterRoot, CharacterArmature, and IK/Pole controls."""
    root_obj = arm_obj.parent or bpy.data.objects.get("CharacterRoot")
    targets = [arm_obj]
    if root_obj is not None:
        targets.append(root_obj)
    for side in ("L", "R"):
        ik_obj = bpy.data.objects.get(IK_TARGET_NAMES[side])
        pole_obj = bpy.data.objects.get(POLE_TARGET_NAMES[side])
        if ik_obj is not None:
            targets.append(ik_obj)
        if pole_obj is not None:
            targets.append(pole_obj)

    for obj in targets:
        if obj.animation_data is not None:
            obj.animation_data_clear()


def _keyframe_walk_frame(
    arm_obj: bpy.types.Object,
    root_obj: bpy.types.Object,
    frame: int,
) -> None:
    """Insert Blender keyframes on CharacterRoot, IK/Pole targets, and PoseBones."""
    root_obj.keyframe_insert(data_path="location", frame=frame)
    root_obj.keyframe_insert(data_path="rotation_euler", frame=frame)

    for side in ("L", "R"):
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]
        ik_obj.keyframe_insert(data_path="location", frame=frame)
        ik_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        if "is_locked" in ik_obj:
            ik_obj.keyframe_insert(data_path='["is_locked"]', frame=frame)
        pole_obj.keyframe_insert(data_path="location", frame=frame)

    animated_bones = (
        "root",
        "pelvis",
        "spine",
        "neck",
        "head",
        "shoulder.L",
        "upper_arm.L",
        "forearm.L",
        "hand.L",
        "shoulder.R",
        "upper_arm.R",
        "forearm.R",
        "hand.R",
        "thigh.L",
        "shin.L",
        "foot.L",
        "thigh.R",
        "shin.R",
        "foot.R",
    )
    for bone_name in animated_bones:
        pbone = arm_obj.pose.bones.get(bone_name)
        if pbone is not None:
            pbone.keyframe_insert(data_path="location", frame=frame)
            pbone.keyframe_insert(data_path="rotation_euler", frame=frame)


def generate_walk_cycle(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
) -> dict:
    """Generate and keyframe a 48-frame in-place procedural walk cycle."""
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    if root_obj is None:
        raise RuntimeError("CharacterRoot object not found")

    scene = bpy.context.scene
    cycle_frames = config.walk_cycle_frames
    scene.render.fps = config.fps
    scene.frame_start = 1
    scene.frame_end = cycle_frames

    start_x, start_y, start_z = character_start_location(config)
    root_obj.location = Vector((start_x, start_y, start_z))
    root_obj.rotation_euler = (0.0, 0.0, 0.0)

    reset_pose(arm)
    setup_leg_ik(arm)
    reset_leg_ik(arm)
    _clear_existing_animation_data(arm)

    # Keep FootIK and KneePole in unified World Space across all frames so F-Curves never mix parent spaces
    lock_foot_contact(arm, "L", contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0))
    lock_foot_contact(arm, "R", contact_world_xyz=(start_x + HIP_X_OFFSET, start_y, 0.0))

    frame_records: List[dict] = []
    unreachable_events: List[dict] = []

    # Generate frames 1 .. cycle_frames + 1 (frame 49 closes the loop identically to frame 1)
    for frame in range(1, cycle_frames + 2):
        scene.frame_set(frame)
        u = ((frame - 1) % cycle_frames) / float(cycle_frames)
        theta = 2.0 * math.pi * u
        sin_t = math.sin(theta)
        cos_2t = math.cos(2.0 * theta)

        # Keep CharacterRoot strictly stationary at start waypoint
        root_obj.location = Vector((start_x, start_y, start_z))
        root_obj.rotation_euler = (0.0, 0.0, 0.0)

        # 1. Pelvis translation & rotation
        # Remember: for vertical axial bones (`pelvis`), local +X = World +X, local +Y = World +Z, local +Z = World -Y
        pelvis_dx = -config.walk_pelvis_sway_amp * sin_t
        pelvis_dz = config.walk_pelvis_crouch - config.walk_pelvis_bob_amp * cos_2t
        set_bone_location(arm, "pelvis", (pelvis_dx, pelvis_dz, 0.0), update=False)

        pelvis_rx = -1.5 + 1.0 * cos_2t  # Subtle forward pitch oscillation
        pelvis_ry = config.walk_pelvis_yaw_deg * sin_t
        pelvis_rz = config.walk_pelvis_roll_deg * sin_t
        set_bone_rotation(arm, "pelvis", (pelvis_rx, pelvis_ry, pelvis_rz), update=False)

        # 2. Spine counter-rotation & subtle forward lean
        spine_rx = -config.walk_torso_lean_deg - 0.8 * cos_2t
        spine_ry = -config.walk_torso_yaw_deg * sin_t
        spine_rz = -0.6 * pelvis_rz
        set_bone_rotation(arm, "spine", (spine_rx, spine_ry, spine_rz), update=False)

        # 3. Neck & Head stabilization (counter-rotating to keep head level and steady)
        total_body_rx = pelvis_rx + spine_rx
        total_body_ry = pelvis_ry + spine_ry
        total_body_rz = pelvis_rz + spine_rz
        set_bone_rotation(
            arm,
            "neck",
            (-0.45 * total_body_rx, -0.45 * total_body_ry, -0.45 * total_body_rz),
            update=False,
        )
        set_bone_rotation(
            arm,
            "head",
            (-0.45 * total_body_rx, -0.45 * total_body_ry, -0.45 * total_body_rz),
            update=False,
        )

        # 4. Contra-lateral Arm Swing:
        # u in (0.0, 0.5) => sin_t > 0 => Right leg swings forward (+Y), so Left arm swings forward (+X rot)
        # u in (0.5, 1.0) => sin_t < 0 => Left leg swings forward (+Y), so Right arm swings forward (+X rot)
        arm_l_rx = config.walk_arm_swing_deg * sin_t
        arm_r_rx = -config.walk_arm_swing_deg * sin_t
        elbow_l_rx = config.walk_elbow_base_deg + config.walk_elbow_swing_deg * max(0.0, sin_t)
        elbow_r_rx = config.walk_elbow_base_deg + config.walk_elbow_swing_deg * max(0.0, -sin_t)

        set_bone_rotation(arm, "upper_arm.L", (arm_l_rx, 0.0, -4.0), update=False)
        set_bone_rotation(arm, "forearm.L", (elbow_l_rx, 0.0, 0.0), update=False)
        set_bone_rotation(arm, "upper_arm.R", (arm_r_rx, 0.0, 4.0), update=False)
        set_bone_rotation(arm, "forearm.R", (elbow_r_rx, 0.0, 0.0), update=True)

        # 5. Leg Stance & Swing control via Task 4D Foot Contact + Task 4C IK
        if u <= 0.5:
            # Left leg is in Stance Phase (locked at frame 1, evaluated across frames 2..25)
            if frame == 1 or frame == cycle_frames + 1:
                state_l = lock_foot_contact(
                    arm,
                    "L",
                    contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
            else:
                state_l = evaluate_foot_support(arm, "L")

            if u == 0.0 or abs(u - 0.5) < 1e-6:
                state_r = lock_foot_contact(
                    arm,
                    "R",
                    contact_world_xyz=(start_x + HIP_X_OFFSET, start_y, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
                phase_r = "stance"
            else:
                swing_s_r = u / 0.5
                y_off_r, z_lift_r = compute_swing_trajectory(
                    swing_s_r, config.walk_step_length, config.walk_step_height
                )
                unlock_foot_contact(arm, "R", reparent_to_root=False)
                set_foot_ik_target(
                    arm,
                    "R",
                    (start_x + HIP_X_OFFSET, start_y + y_off_r, start_z + ANKLE_REST_Z + z_lift_r),
                    foot_rotation_deg=(0.0, 0.0, 0.0),
                )
                state_r = evaluate_foot_support(arm, "R")
                phase_r = "swing"
            phase_l = "stance"
        else:
            # Right leg is in Stance Phase (locked at frame 25, evaluated across frames 26..48)
            state_r = evaluate_foot_support(arm, "R")
            swing_s_l = (u - 0.5) / 0.5
            y_off_l, z_lift_l = compute_swing_trajectory(
                swing_s_l, config.walk_step_length, config.walk_step_height
            )
            unlock_foot_contact(arm, "L", reparent_to_root=False)
            set_foot_ik_target(
                arm,
                "L",
                (start_x - HIP_X_OFFSET, start_y + y_off_l, start_z + ANKLE_REST_Z + z_lift_l),
                foot_rotation_deg=(0.0, 0.0, 0.0),
            )
            state_l = evaluate_foot_support(arm, "L")
            phase_l = "swing"
            phase_r = "stance"

        if not state_l["is_reachable"]:
            unreachable_events.append({"frame": frame, "side": "L", "dist": state_l["hip_to_target_dist"]})
        if not state_r["is_reachable"]:
            unreachable_events.append({"frame": frame, "side": "R", "dist": state_r["hip_to_target_dist"]})

        _keyframe_walk_frame(arm, root_obj, frame)

        if frame <= cycle_frames:
            frame_records.append({
                "frame": frame,
                "u": round(u, 4),
                "phase_l": phase_l,
                "phase_r": phase_r,
                "state_l": state_l,
                "state_r": state_r,
                "arm_l_rx": round(arm_l_rx, 2),
                "arm_r_rx": round(arm_r_rx, 2),
            })

    if unreachable_events:
        raise RuntimeError(f"Encountered unreachable IK states during walk cycle: {unreachable_events}")

    print(f"[WALK_CYCLE] Keyframed {cycle_frames}-frame procedural walk cycle (@ {config.fps} FPS)")
    return {
        "cycle_frames": cycle_frames,
        "fps": config.fps,
        "frame_records": frame_records,
        "unreachable_count": len(unreachable_events),
    }
