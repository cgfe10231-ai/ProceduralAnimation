"""Procedural start, acceleration, steady walking, deceleration, and stop generator (Task 5C).

Generates a 204-frame (8.5s @ 24 FPS) continuous locomotion sequence:
  Idle Stand -> Start -> Accelerate -> Steady Walk -> Decelerate -> Stop Stand

Key Properties:
- Reuses Task 4C two-bone leg IK (`FootIK.L/R`, `KneePole.L/R`), Task 4D support-foot
  locking (`lock_foot_contact`, `unlock_foot_contact`, `evaluate_foot_support`,
  `move_character_root_with_support`), and Task 5A/5B gait & upper-body coordination.
- Drives `CharacterRoot` forward (+Y) via a C1-smooth analytical velocity profile `v(tau)`
  that starts at 0.0 m/s, accelerates smoothly to `target_speed = 0.24 m/s`, maintains
  constant speed across 3 steady steps, decelerates smoothly back to 0.0 m/s, and holds 0.0 m/s.
- Synchronizes step lengths, step durations (cadence), stance lock points, and gait phase `u(tau)`
  with the variable-speed root trajectory rather than overlaying a fixed-speed walk cycle.
- Parameterizes subtle, smooth pelvis lowering and torso forward lean / recovery during
  acceleration and deceleration without exaggerated wind-up motions.
- Ends with a closing step bringing both feet cleanly side-by-side on `Z = 0.0` at `Y = -6.74 m`
  with zero frame jumps or IK reach violations.
"""

import math
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

from src.character.builder import character_start_location
from src.config import PipelineConfig
from src.motion.forward_walk import compute_forward_swing_point
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


def _smoothstep01(x: float) -> float:
    """C1 cosine smoothstep on [0, 1]."""
    t = max(0.0, min(1.0, x))
    return 0.5 * (1.0 - math.cos(math.pi * t))


def _smooth_bell01(x: float) -> float:
    """C1 bell curve sin^2(pi * x) on [0, 1], peaking at 1.0 when x = 0.5."""
    t = max(0.0, min(1.0, x))
    return math.sin(math.pi * t) ** 2


def evaluate_root_kinematics(tau: float, config: PipelineConfig) -> Tuple[float, float, str]:
    """Return (root_y_displacement, speed_mps, motion_stage) at frame offset `tau = frame - 1`.

    Uses a C1-continuous velocity curve `v(tau)` (in m/frame) and its exact analytical integral:
    - [0, tau_s]: Idle Stand (`v = 0`)
    - [tau_s, tau_a]: Start & Accelerate (`v` ramps 0 -> v_max via cosine smoothstep)
    - [tau_a, tau_w]: Steady Walk (`v = v_max` constant)
    - [tau_w, tau_d]: Decelerate & Stop (`v` ramps v_max -> 0 via cosine smoothstep)
    - [tau_d, end]: Final Stand (`v = 0`)
    """
    fps = float(config.fps)
    v_max_pf = config.start_stop_target_speed / fps  # 0.010 m/frame @ 24 FPS

    t_s = float(config.start_stop_stand_start_frames)  # 12
    dur_a = float(config.start_stop_accel_frames)      # 54
    dur_w = float(config.start_stop_steady_frames)     # 72
    dur_d = float(config.start_stop_decel_frames)      # 54

    t_a = t_s + dur_a          # 66
    t_w = t_a + dur_w          # 138
    t_d = t_w + dur_d          # 192

    disp_a_total = 0.5 * v_max_pf * dur_a
    disp_w_total = v_max_pf * dur_w
    disp_d_total = 0.5 * v_max_pf * dur_d

    if tau <= t_s:
        return 0.0, 0.0, "stand_start"

    if tau <= t_a:
        dt = tau - t_s
        v_pf = 0.5 * v_max_pf * (1.0 - math.cos(math.pi * dt / dur_a))
        disp = 0.5 * v_max_pf * (dt - (dur_a / math.pi) * math.sin(math.pi * dt / dur_a))
        stage = "start" if dt < 30.0 else "accelerate"
        return disp, v_pf * fps, stage

    if tau <= t_w:
        dt = tau - t_a
        v_pf = v_max_pf
        disp = disp_a_total + v_max_pf * dt
        return disp, v_pf * fps, "steady_walk"

    if tau <= t_d:
        dt = tau - t_w
        v_pf = 0.5 * v_max_pf * (1.0 + math.cos(math.pi * dt / dur_d))
        disp = (
            disp_a_total
            + disp_w_total
            + 0.5 * v_max_pf * (dt + (dur_d / math.pi) * math.sin(math.pi * dt / dur_d))
        )
        stage = "decelerate" if dt < 24.0 else "stop_step"
        return disp, v_pf * fps, stage

    return disp_a_total + disp_w_total + disp_d_total, 0.0, "stand_stop"


def build_step_schedule(config: PipelineConfig, start_y: float) -> List[dict]:
    """Build the 7 coordinated half-steps bridging `start_y = -8.00 m` to `stop_y = -6.74 m`.

    Each step specifies:
    - `k`: step index 0..6
    - `tau_start`, `tau_end`: frame offset interval `[tau_start, tau_end]`
    - `stance_side`: 'L' (even k) or 'R' (odd k)
    - `swing_side`: 'R' (even k) or 'L' (odd k)
    - `stance_y`: world Y where the stance foot is locked
    - `swing_y_start`, `swing_y_end`: world Y start and landing targets for the swing foot
    - `step_length`: forward lead of landing foot relative to stance foot (`swing_y_end - stance_y`)
    - `swing_span`: total forward travel of the swinging foot (`swing_y_end - swing_y_start`)
    - `step_height`: vertical clearance of the swing foot
    - `stage_name`: descriptive phase label
    """
    l_init = config.start_stop_init_step_length      # 0.15 m
    l_steady = config.start_stop_steady_step_length  # 0.24 m
    h_steady = config.forward_walk_step_height       # 0.14 m

    y0 = start_y                                     # -8.00 m
    y1 = y0 + l_init                                 # -7.85 m (Step 0 R landing)
    y2 = y1 + l_steady                               # -7.61 m (Step 1 L landing)
    y3 = y2 + l_steady                               # -7.37 m (Step 2 R landing)
    y4 = y3 + l_steady                               # -7.13 m (Step 3 L landing)
    y5 = y4 + l_steady                               # -6.89 m (Step 4 R landing)
    y6 = y5 + l_init                                 # -6.74 m (Step 5 L landing == final stop Y)
    y7 = y6                                          # -6.74 m (Step 6 R closing step lands side-by-side)

    raw_steps = [
        # (k, tau_start, tau_end, stance_side, stance_y, swing_y_start, swing_y_end, step_height, stage_name)
        (0, 12, 42, "L", y0, y0, y1, 0.10, "start"),
        (1, 42, 66, "R", y1, y0, y2, 0.13, "accelerate"),
        (2, 66, 90, "L", y2, y1, y3, h_steady, "steady_walk"),
        (3, 90, 114, "R", y3, y2, y4, h_steady, "steady_walk"),
        (4, 114, 138, "L", y4, y3, y5, h_steady, "steady_walk"),
        (5, 138, 162, "R", y5, y4, y6, 0.12, "decelerate"),
        (6, 162, 192, "L", y6, y5, y7, 0.09, "stop_step"),
    ]

    schedule: List[dict] = []
    for k, ts, te, st_side, st_y, sw_y0, sw_y1, sh, stg in raw_steps:
        sw_side = "R" if st_side == "L" else "L"
        schedule.append({
            "k": k,
            "tau_start": ts,
            "tau_end": te,
            "duration_frames": te - ts,
            "stance_side": st_side,
            "swing_side": sw_side,
            "stance_y": round(st_y, 5),
            "swing_y_start": round(sw_y0, 5),
            "swing_y_end": round(sw_y1, 5),
            "step_length": round(sw_y1 - st_y, 5),
            "swing_span": round(sw_y1 - sw_y0, 5),
            "step_height": sh,
            "stage_name": stg,
        })
    return schedule


def _evaluate_gait_phase_and_envelopes(
    tau: int,
    config: PipelineConfig,
    schedule: List[dict],
) -> Tuple[float, float, float, float, float, Optional[dict]]:
    """Compute step-synchronized gait phase `u` in [0, 1), cyclic motion amplitude `gait_amp`,
    base crouch envelope `crouch_env`, transient pelvis drop `trans_drop`, and transient
    torso lean `trans_lean_deg` at frame offset `tau`.
    """
    t_s = config.start_stop_stand_start_frames  # 12
    t_a = t_s + config.start_stop_accel_frames  # 66
    t_w = t_a + config.start_stop_steady_frames # 138
    t_d = t_w + config.start_stop_decel_frames  # 192
    t_end = config.start_stop_total_frames - 1  # 203

    active_step: Optional[dict] = None
    for step in schedule:
        if step["tau_start"] <= tau < step["tau_end"]:
            active_step = step
            break

    if active_step is None:
        u = 0.0
    else:
        s = (tau - active_step["tau_start"]) / float(active_step["duration_frames"])
        if active_step["stance_side"] == "L":
            u = 0.5 * s
        else:
            u = 0.5 + 0.5 * s

    # Locomotion amplitude envelope `gait_amp` in [0, 1]:
    # Ramps 0 -> 1 over the first step [12, 42], stays 1.0 across [42, 162], ramps 1 -> 0 over [162, 192]
    if tau <= t_s or tau >= t_d:
        gait_amp = 0.0
    elif tau < 42:
        gait_amp = _smoothstep01((tau - t_s) / 30.0)
    elif tau <= 162:
        gait_amp = 1.0
    else:
        gait_amp = 1.0 - _smoothstep01((tau - 162) / 30.0)

    # Base pelvis crouch envelope `crouch_env` in [0, 1]:
    # Smoothly lowers pelvis during initial stand [4, 12] prior to step-off and recovers during [192, 200]
    if tau <= 4 or tau >= 200:
        crouch_env = 0.0
    elif tau < t_s:
        crouch_env = _smoothstep01((tau - 4) / float(t_s - 4))
    elif tau <= t_d:
        crouch_env = 1.0
    else:
        crouch_env = 1.0 - _smoothstep01((tau - t_d) / 8.0)

    # Subtle parameterized start/acceleration and deceleration/braking posture adjustments
    if t_s <= tau <= t_a:
        bell_a = _smooth_bell01((tau - t_s) / float(t_a - t_s))
        trans_drop = config.start_stop_accel_pelvis_drop * bell_a
        trans_lean_deg = config.start_stop_accel_torso_lean_deg * bell_a
    elif t_w <= tau <= t_d:
        bell_d = _smooth_bell01((tau - t_w) / float(t_d - t_w))
        trans_drop = config.start_stop_accel_pelvis_drop * bell_d
        trans_lean_deg = config.start_stop_decel_torso_lean_deg * bell_d
    else:
        trans_drop = 0.0
        trans_lean_deg = 0.0

    return u, gait_amp, crouch_env, trans_drop, trans_lean_deg, active_step


def _apply_start_stop_upper_body_pose(
    arm: bpy.types.Object,
    config: PipelineConfig,
    u: float,
    gait_amp: float,
    crouch_env: float,
    trans_drop: float,
    trans_lean_deg: float,
    prep_shift_x: float = 0.0,
) -> Tuple[float, float, float, float]:
    """Apply existing pelvis/spine/neck/head/arm control logic scaled by `gait_amp` and
    parameterized start/stop transition adjustments.

    Returns (pelvis_dz, torso_world_pitch_deg, arm_l_rx, arm_r_rx).
    """
    theta = 2.0 * math.pi * u
    sin_t = math.sin(theta)
    cos_2t = math.cos(2.0 * theta)

    # Preserve existing pelvis control structure with smooth amplitude & transition modulation
    pelvis_dx = -config.walk_pelvis_sway_amp * sin_t * gait_amp + prep_shift_x
    pelvis_dz = (
        config.forward_walk_pelvis_crouch * crouch_env
        - config.walk_pelvis_bob_amp * cos_2t * gait_amp
        + trans_drop
    )
    set_bone_location(arm, "pelvis", (pelvis_dx, pelvis_dz, 0.0), update=False)

    pelvis_rx = (-1.5 * crouch_env) + (1.0 * cos_2t * gait_amp)
    pelvis_ry = config.walk_pelvis_yaw_deg * sin_t * gait_amp
    pelvis_rz = config.walk_pelvis_roll_deg * sin_t * gait_amp
    set_bone_rotation(arm, "pelvis", (pelvis_rx, pelvis_ry, pelvis_rz), update=False)

    spine_rx = (
        -config.walk_torso_lean_deg * gait_amp
        - 0.8 * cos_2t * gait_amp
        - trans_lean_deg
    )
    spine_ry = -config.walk_torso_yaw_deg * sin_t * gait_amp
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

    arm_l_rx = config.walk_arm_swing_deg * sin_t * gait_amp
    arm_r_rx = -config.walk_arm_swing_deg * sin_t * gait_amp
    elbow_l_rx = (
        config.walk_elbow_base_deg * crouch_env
        + config.walk_elbow_swing_deg * max(0.0, sin_t) * gait_amp
    )
    elbow_r_rx = (
        config.walk_elbow_base_deg * crouch_env
        + config.walk_elbow_swing_deg * max(0.0, -sin_t) * gait_amp
    )

    set_bone_rotation(arm, "upper_arm.L", (arm_l_rx, 0.0, -4.0), update=False)
    set_bone_rotation(arm, "forearm.L", (elbow_l_rx, 0.0, 0.0), update=False)
    set_bone_rotation(arm, "upper_arm.R", (arm_r_rx, 0.0, 4.0), update=False)
    set_bone_rotation(arm, "forearm.R", (elbow_r_rx, 0.0, 0.0), update=True)

    torso_pitch_deg = -(pelvis_rx + spine_rx)
    return pelvis_dz, torso_pitch_deg, arm_l_rx, arm_r_rx


def generate_start_stop_walk(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
) -> dict:
    """Generate and keyframe the 204-frame start -> accelerate -> steady -> decelerate -> stop sequence."""
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    if root_obj is None:
        raise RuntimeError("CharacterRoot object not found")

    scene = bpy.context.scene
    total_frames = config.start_stop_total_frames
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

    schedule = build_step_schedule(config, start_y)
    t_s = config.start_stop_stand_start_frames  # 12
    t_d = (
        config.start_stop_stand_start_frames
        + config.start_stop_accel_frames
        + config.start_stop_steady_frames
        + config.start_stop_decel_frames
    )  # 192
    stop_y = schedule[-1]["swing_y_end"]

    frame_records: List[dict] = []
    unreachable_events: List[dict] = []

    for frame in range(1, total_frames + 1):
        scene.frame_set(frame)
        tau = frame - 1

        disp_y, speed_mps, stage = evaluate_root_kinematics(tau, config)
        root_y = start_y + disp_y
        root_world = (start_x, root_y, start_z)

        u, gait_amp, crouch_env, trans_drop, trans_lean_deg, active_step = (
            _evaluate_gait_phase_and_envelopes(tau, config, schedule)
        )

        # Gentle lateral weight shift onto initial stance leg (L) right around step-off, and back to 0 at stop
        prep_shift_x = 0.0
        if 6 <= tau <= 18:
            prep_shift_x = -0.008 * _smooth_bell01((tau - 6) / 12.0)

        move_character_root_with_support(arm, root_world)
        pelvis_dz, torso_lean, arm_l_rx, arm_r_rx = _apply_start_stop_upper_body_pose(
            arm,
            config,
            u=u,
            gait_amp=gait_amp,
            crouch_env=crouch_env,
            trans_drop=trans_drop,
            trans_lean_deg=trans_lean_deg,
            prep_shift_x=prep_shift_x,
        )

        if tau < t_s:
            # Phase 1: Initial Idle Stand (both feet locked side-by-side at start_y)
            if tau == 0:
                state_l = lock_foot_contact(
                    arm,
                    "L",
                    contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
                state_r = lock_foot_contact(
                    arm,
                    "R",
                    contact_world_xyz=(start_x + HIP_X_OFFSET, start_y, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
            else:
                state_l = evaluate_foot_support(arm, "L")
                state_r = evaluate_foot_support(arm, "R")
            phase_l, phase_r = "stance", "stance"
            step_idx = -1

        elif tau >= t_d:
            # Phase 5: Final Stop Stand (both feet locked side-by-side at stop_y)
            if tau == t_d:
                state_l = lock_foot_contact(
                    arm,
                    "L",
                    contact_world_xyz=(start_x - HIP_X_OFFSET, stop_y, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
                state_r = lock_foot_contact(
                    arm,
                    "R",
                    contact_world_xyz=(start_x + HIP_X_OFFSET, stop_y, 0.0),
                    target_rotation_deg=(0.0, 0.0, 0.0),
                )
            else:
                state_l = evaluate_foot_support(arm, "L")
                state_r = evaluate_foot_support(arm, "R")
            phase_l, phase_r = "stance", "stance"
            step_idx = len(schedule)

        else:
            # Phases 2..4: Active locomotion steps k = 0..6
            assert active_step is not None
            step_idx = active_step["k"]
            s = (tau - active_step["tau_start"]) / float(active_step["duration_frames"])
            y_swing, z_lift = compute_forward_swing_point(
                active_step["swing_y_start"],
                active_step["swing_y_end"],
                s,
                active_step["step_height"],
            )

            if active_step["stance_side"] == "L":
                if tau == active_step["tau_start"]:
                    state_l = lock_foot_contact(
                        arm,
                        "L",
                        contact_world_xyz=(start_x - HIP_X_OFFSET, active_step["stance_y"], 0.0),
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
                if tau == active_step["tau_start"]:
                    state_r = lock_foot_contact(
                        arm,
                        "R",
                        contact_world_xyz=(start_x + HIP_X_OFFSET, active_step["stance_y"], 0.0),
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
            "tau": tau,
            "stage": stage,
            "step_k": step_idx,
            "u": round(u, 4),
            "gait_amp": round(gait_amp, 4),
            "root_y": round(root_y, 5),
            "speed_mps": round(speed_mps, 5),
            "pelvis_dz": round(pelvis_dz, 5),
            "torso_lean_deg": round(torso_lean, 3),
            "phase_l": phase_l,
            "phase_r": phase_r,
            "state_l": state_l,
            "state_r": state_r,
            "arm_l_rx": round(arm_l_rx, 2),
            "arm_r_rx": round(arm_r_rx, 2),
        })

    if unreachable_events:
        raise RuntimeError(
            f"Encountered {len(unreachable_events)} IK reach violations during start-stop walk: "
            f"{unreachable_events[:5]}"
        )

    total_disp = frame_records[-1]["root_y"] - frame_records[0]["root_y"]
    peak_speed = max(r["speed_mps"] for r in frame_records)

    print(
        f"[START_STOP_WALK] Keyframed {total_frames} frames (@ {config.fps} FPS): "
        f"root Y {frame_records[0]['root_y']:.4f}m -> {frame_records[-1]['root_y']:.4f}m "
        f"(disp={total_disp:.4f}m, peak_speed={peak_speed:.4f}m/s, steps={len(schedule)}), "
        f"unreachable_events=0"
    )
    return {
        "total_frames": total_frames,
        "fps": config.fps,
        "total_root_displacement": total_disp,
        "peak_speed_mps": peak_speed,
        "unreachable_count": len(unreachable_events),
        "step_schedule": schedule,
        "frame_records": frame_records,
    }
