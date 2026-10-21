"""Explosive start and sprint acceleration (`SprintStartAction`) in the unified motion framework (Task 6C).

Sequence: static set (crouch + forward lean) -> push-off -> burst acceleration -> steady sprint.

Design (all inside the Task 6A framework; reuses Task 6B swing profile, the contact adapter,
IK and keyframing):
- Root: analytic burst velocity v(x) = vmax * (2x - x^2), x = dt / accel_frames
  (non-zero initial acceleration, C1 arrival at vmax), then constant vmax.
- Gait: a variable-length step schedule. Step duration, stance frames, flight frames and swing
  height are interpolated from the root speed at the moment each step begins, so cadence rises
  and stance shortens while flight and stride grow. Each stance foot is planted where the root
  will be at mid-stance, so no contact point is moved to hide reach violations
  (the action raises if the IK target is ever clamped).
- Step k stance foot is locked at its world position for S_k frames; both feet are released
  during flight. The foot of step j swings from stance_y(j) to stance_y(j+2).
- A continuous warped step phase psi (stance -> [0, .5), flight -> [.5, 1)) drives pelvis bounce
  and arm/torso rotation so posture is continuous across variable-length steps.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import bpy

from src.config import PipelineConfig
from src.motion.framework import (
    ActionExecutionResult,
    ContactPointState,
    MotionAction,
    MotionMode,
    MotionPlanner,
    MotionRuntimeContext,
    MotionState,
    forward_unit_vector_from_yaw,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.motion.run_cycle import compute_run_swing_point
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, IK_TARGET_NAMES
from src.rig.pose import set_bone_location, set_bone_rotation


def _smoothstep01(x: float) -> float:
    t = max(0.0, min(1.0, x))
    return 0.5 * (1.0 - math.cos(math.pi * t))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def evaluate_sprint_root_kinematics(tau: float, config: PipelineConfig) -> Tuple[float, float, float, str]:
    """Return `(root_disp_m, speed_mps, accel_mps2, stage)` at frame offset `tau` (valid for any tau >= 0)."""
    fps = float(config.fps)
    vmax = config.sprint_target_speed
    v_pf = vmax / fps
    p = float(config.sprint_prep_frames)
    a_f = float(config.sprint_accel_frames)
    if tau <= p:
        return 0.0, 0.0, 0.0, "prep"
    if tau <= p + a_f:
        dt = tau - p
        x = dt / a_f
        disp = v_pf * a_f * (x * x - x ** 3 / 3.0)
        speed = vmax * (2.0 * x - x * x)
        accel = vmax * 2.0 / (a_f / fps) * (1.0 - x)
        stage = "start" if dt < config.sprint_start_frames else "accelerate"
        return disp, speed, accel, stage
    disp = v_pf * a_f * (2.0 / 3.0) + v_pf * (tau - p - a_f)
    return disp, vmax, 0.0, "sprint"


def build_sprint_schedule(config: PipelineConfig, start_y: float) -> List[dict]:
    """Build the variable step schedule (tau units). Extends past the action end for swing look-ahead."""
    vmax = config.sprint_target_speed
    total = config.sprint_total_frames
    steps: List[dict] = []
    t = config.sprint_prep_frames
    k = 0
    while t < total + 40:
        _, v, _, _ = evaluate_sprint_root_kinematics(t, config)
        r = v / vmax
        d = int(round(_lerp(config.sprint_step_frames_start, config.sprint_step_frames_sprint, r)))
        s = int(round(_lerp(config.sprint_stance_frames_start, config.sprint_stance_frames_sprint, r)))
        s = max(2, min(s, d - 2))
        mid = t + (s - 1) / 2.0
        stance_y = start_y if k == 0 else start_y + evaluate_sprint_root_kinematics(mid, config)[0]
        steps.append({
            "k": k,
            "tau_start": t,
            "duration_frames": d,
            "stance_frames": s,
            "flight_frames": d - s,
            "tau_end": t + d,
            "stance_side": "L" if k % 2 == 0 else "R",
            "swing_side": "R" if k % 2 == 0 else "L",
            "stance_y": round(stance_y, 6),
            "speed_at_start": round(v, 5),
            "step_height": _lerp(config.sprint_step_height_start, config.sprint_step_height_sprint, r),
        })
        t += d
        k += 1
    for i in range(len(steps) - 1):
        steps[i]["step_length"] = round(steps[i + 1]["stance_y"] - steps[i]["stance_y"], 6)
    steps[-1]["step_length"] = steps[-2]["step_length"]
    for st in steps:
        st["cadence_steps_per_s"] = round(config.fps / float(st["duration_frames"]), 4)
    return steps


def apply_sprint_pose(
    arm: bpy.types.Object,
    config: PipelineConfig,
    tau: int,
    u: float,
    amp: float,
) -> Tuple[float, float, float, float]:
    """Pelvis crouch/bounce, forward lean, head stabilization and arm drive.

    Returns `(pelvis_dz, torso_pitch_deg, arm_l_rx, arm_r_rx)`.
    """
    p = float(config.sprint_prep_frames)
    a_f = float(config.sprint_accel_frames)
    prep_prog = _smoothstep01(tau / p)
    accel_prog = _smoothstep01((tau - p) / a_f)

    crouch = _lerp(0.0, config.sprint_crouch_start, prep_prog)
    crouch = _lerp(crouch, config.sprint_pelvis_base_z, accel_prog)
    lean = _lerp(0.0, config.sprint_lean_start_deg, prep_prog)
    lean = _lerp(lean, config.sprint_lean_sprint_deg, accel_prog)
    lean_frac = lean / config.sprint_lean_start_deg

    theta = 2.0 * math.pi * u
    sin_t = math.sin(theta)
    sin_2t = math.sin(2.0 * theta)
    cos_2t = math.cos(2.0 * theta)

    dz = crouch - config.sprint_pelvis_bounce_amp * amp * sin_2t
    set_bone_location(arm, "pelvis", (-0.014 * amp * sin_t, dz, 0.0), update=False)

    pelvis_rx = -3.0 * lean_frac - 1.2 * amp * cos_2t
    pelvis_ry = 7.5 * amp * sin_t
    pelvis_rz = 3.0 * amp * sin_t
    set_bone_rotation(arm, "pelvis", (pelvis_rx, pelvis_ry, pelvis_rz), update=False)

    spine_rx = -lean + 1.0 * amp * cos_2t
    spine_ry = -9.5 * amp * sin_t
    spine_rz = -0.6 * pelvis_rz
    set_bone_rotation(arm, "spine", (spine_rx, spine_ry, spine_rz), update=False)

    tot = (pelvis_rx + spine_rx, pelvis_ry + spine_ry, pelvis_rz + spine_rz)
    for bone in ("neck", "head"):
        set_bone_rotation(arm, bone, (-0.45 * tot[0], -0.45 * tot[1], -0.45 * tot[2]), update=False)

    # Arms: cocked (L forward / R back) during set, driven contra-laterally once running.
    cock = 18.0 * prep_prog * (1.0 - amp)
    arm_l = config.sprint_arm_swing_deg * amp * sin_t + cock
    arm_r = -config.sprint_arm_swing_deg * amp * sin_t - cock
    elbow_base = config.run_elbow_base_deg * (0.4 * prep_prog + 0.6 * accel_prog)
    elbow_l = elbow_base + config.run_elbow_swing_deg * amp * max(0.0, sin_t)
    elbow_r = elbow_base + config.run_elbow_swing_deg * amp * max(0.0, -sin_t)
    set_bone_rotation(arm, "upper_arm.L", (arm_l, 0.0, -5.0), update=False)
    set_bone_rotation(arm, "forearm.L", (elbow_l, 0.0, 0.0), update=False)
    set_bone_rotation(arm, "upper_arm.R", (arm_r, 0.0, 5.0), update=False)
    set_bone_rotation(arm, "forearm.R", (elbow_r, 0.0, 0.0), update=True)

    return dz, -(pelvis_rx + spine_rx), arm_l, arm_r


STAGE_TO_MODE: Dict[str, MotionMode] = {
    "prep": MotionMode.IDLE,
    "start": MotionMode.START,
    "accelerate": MotionMode.ACCELERATE,
    "sprint": MotionMode.SPRINT,
}


class SprintStartAction(MotionAction):
    """Explosive start (set -> push-off -> burst acceleration) into steady sprint.

    Ends in SPRINT mode with non-zero world velocity, gait phase and live contact states so a
    following action can inherit momentum.
    """

    @property
    def name(self) -> str:
        return "sprint_start"

    def can_start_from(self, state: MotionState) -> bool:
        return state.mode in (MotionMode.IDLE, MotionMode.STOP) and not state.is_airborne

    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
        _ = initial_state
        return config.sprint_total_frames

    def execute(self, initial_state: MotionState, context: MotionRuntimeContext) -> ActionExecutionResult:
        if not self.can_start_from(initial_state):
            raise ValueError(f"SprintStartAction cannot start from mode={initial_state.mode}")

        config = context.config
        scene = context.scene

        bridge_executor = getattr(context, "bridge_executor", None)
        if bridge_executor is None:
            bridge_executor = KinematicBridgeExecutor(
                armature_obj=context.armature_obj,
                root_obj=context.root_obj,
                environment=context.environment,
                default_fps=config.fps,
            )

        env = context.environment
        fps = float(config.fps)
        total = config.sprint_total_frames
        prep = config.sprint_prep_frames

        start_frame = initial_state.frame
        sx, sy, _ = initial_state.position
        yaw = initial_state.yaw_deg
        fx, fy, _ = forward_unit_vector_from_yaw(yaw)
        x_of = {"L": sx - HIP_X_OFFSET, "R": sx + HIP_X_OFFSET}

        steps = build_sprint_schedule(config, sy)

        def stance_y(j: int) -> float:
            return sy if j <= 0 else steps[j]["stance_y"]

        def swing_end_of_support(j: int) -> float:
            return float(steps[0]["tau_start"]) if j < 0 else float(steps[j]["tau_start"] + steps[j]["stance_frames"] - 1)

        states: List[MotionState] = []
        records: List[dict] = []
        unreachable: List[dict] = []
        clamp_events: List[dict] = []

        for tau in range(total):
            frame = start_frame + tau
            scene.frame_set(frame)

            disp, speed, accel, stage = evaluate_sprint_root_kinematics(tau, config)
            root_y = sy + disp
            root_world = (sx, root_y, env.ground_height_at(sx, root_y))
            amp = _smoothstep01((tau - prep) / 30.0)

            active = None
            if tau >= prep:
                for st in steps:
                    if st["tau_start"] <= tau < st["tau_end"]:
                        active = st
                        break
            if active is None:
                psi, k, local, step_s = 0.0, -1, tau, 0
                u = 0.0
            else:
                k = active["k"]
                local = tau - active["tau_start"]
                step_s = active["stance_frames"]
                f = local / float(active["duration_frames"])
                fs = step_s / float(active["duration_frames"])
                psi = 0.5 * f / fs if f < fs else 0.5 + 0.5 * (f - fs) / (1.0 - fs)
                u = ((k % 2) + psi) / 2.0

            p = float(config.sprint_prep_frames)
            a_f = float(config.sprint_accel_frames)
            prep_prog = _smoothstep01(tau / p)
            accel_prog = _smoothstep01((tau - p) / a_f)

            crouch = _lerp(0.0, config.sprint_crouch_start, prep_prog)
            crouch = _lerp(crouch, config.sprint_pelvis_base_z, accel_prog)
            lean = _lerp(0.0, config.sprint_lean_start_deg, prep_prog)
            lean = _lerp(lean, config.sprint_lean_sprint_deg, accel_prog)
            lean_frac = lean / config.sprint_lean_start_deg if config.sprint_lean_start_deg != 0.0 else 0.0

            theta = 2.0 * math.pi * u
            sin_t = math.sin(theta)
            sin_2t = math.sin(2.0 * theta)
            cos_2t = math.cos(2.0 * theta)

            dz = crouch - config.sprint_pelvis_bounce_amp * amp * sin_2t
            pelvis_loc = (-0.014 * amp * sin_t, dz, 0.0)

            pelvis_rx = -3.0 * lean_frac - 1.2 * amp * cos_2t
            pelvis_ry = 7.5 * amp * sin_t
            pelvis_rz = 3.0 * amp * sin_t

            spine_rx = -lean + 1.0 * amp * cos_2t
            spine_ry = -9.5 * amp * sin_t
            spine_rz = -0.6 * pelvis_rz

            tot = (pelvis_rx + spine_rx, pelvis_ry + spine_ry, pelvis_rz + spine_rz)
            neck_rot = (-0.45 * tot[0], -0.45 * tot[1], -0.45 * tot[2])
            head_rot = (-0.45 * tot[0], -0.45 * tot[1], -0.45 * tot[2])

            cock = 18.0 * prep_prog * (1.0 - amp)
            arm_l = config.sprint_arm_swing_deg * amp * sin_t + cock
            arm_r = -config.sprint_arm_swing_deg * amp * sin_t - cock
            elbow_base = config.run_elbow_base_deg * (0.4 * prep_prog + 0.6 * accel_prog)
            elbow_l = elbow_base + config.run_elbow_swing_deg * amp * max(0.0, sin_t)
            elbow_r = elbow_base + config.run_elbow_swing_deg * amp * max(0.0, -sin_t)

            fk_rotations = {
                "upper_arm.L": (arm_l, 0.0, -5.0),
                "forearm.L": (elbow_l, 0.0, 0.0),
                "upper_arm.R": (arm_r, 0.0, 5.0),
                "forearm.R": (elbow_r, 0.0, 0.0),
            }

            if active is None:
                phase_name = "prep"
                z_l = env.ground_height_at(x_of["L"], sy)
                z_r = env.ground_height_at(x_of["R"], sy)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(x_of["L"], sy, z_l + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(x_of["R"], sy, z_r + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                ph_l = ph_r = "stance"
                is_flight = False
            else:
                st_side = active["stance_side"]
                ot_side = active["swing_side"]
                if local < step_s:
                    phase_name = "stance"
                    st_y = stance_y(k)
                    zg_st = env.ground_height_at(x_of[st_side], st_y)
                    foot_tgt_st = PlannedFootTarget(
                        world_xyz=(x_of[st_side], st_y, zg_st + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(0.0, 0.0, yaw),
                        contact_intent=True,
                    )
                    ph_st = "stance"
                    is_flight = False
                else:
                    phase_name = "flight"
                    e = swing_end_of_support(k)
                    t_land = float(steps[k + 2]["tau_start"])
                    s = (tau - e) / (t_land - e) if t_land > e else 0.0
                    hgt = steps[max(k, 0)]["step_height"]
                    y, lift = compute_run_swing_point(stance_y(k), stance_y(k + 2), s, hgt)
                    pitch = -18.0 * math.sin(math.pi * max(0.0, min(1.0, s)))
                    zg = env.ground_height_at(x_of[st_side], y)
                    foot_tgt_st = PlannedFootTarget(
                        world_xyz=(x_of[st_side], y, zg + ANKLE_REST_Z + lift),
                        is_locked=False,
                        rotation_deg=(pitch, 0.0, yaw),
                        contact_intent=False,
                    )
                    ph_st = "flight"
                    is_flight = True

                e_ot = swing_end_of_support(k - 1)
                t_land_ot = float(steps[k + 1]["tau_start"])
                s_ot = (tau - e_ot) / (t_land_ot - e_ot) if t_land_ot > e_ot else 0.0
                hgt_ot = steps[max(k - 1, 0)]["step_height"]
                y_ot, lift_ot = compute_run_swing_point(stance_y(k - 1), stance_y(k + 1), s_ot, hgt_ot)
                pitch_ot = -18.0 * math.sin(math.pi * max(0.0, min(1.0, s_ot)))
                zg_ot = env.ground_height_at(x_of[ot_side], y_ot)
                foot_tgt_ot = PlannedFootTarget(
                    world_xyz=(x_of[ot_side], y_ot, zg_ot + ANKLE_REST_Z + lift_ot),
                    is_locked=False,
                    rotation_deg=(pitch_ot, 0.0, yaw),
                    contact_intent=False,
                )
                ph_ot = "swing" if ph_st == "stance" else "flight"

                if st_side == "L":
                    foot_tgt_l, ph_l = foot_tgt_st, ph_st
                    foot_tgt_r, ph_r = foot_tgt_ot, ph_ot
                else:
                    foot_tgt_r, ph_r = foot_tgt_st, ph_st
                    foot_tgt_l, ph_l = foot_tgt_ot, ph_ot

            mode = STAGE_TO_MODE[stage]
            planned_pose = KinematicPlannedPose(
                frame=frame,
                time_seconds=(frame - 1) / fps,
                root_position=root_world,
                root_yaw_deg=yaw,
                speed_mps=speed,
                accel_mps2=accel,
                motion_mode=mode,
                dt=1.0 / fps,
                pelvis_location=pelvis_loc,
                pelvis_rotation_deg=(pelvis_rx, pelvis_ry, pelvis_rz),
                spine_rotation_deg=(spine_rx, spine_ry, spine_rz),
                neck_rotation_deg=neck_rot,
                head_rotation_deg=head_rot,
                foot_L=foot_tgt_l,
                foot_R=foot_tgt_r,
                hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
                hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
                fk_joint_rotations_deg=fk_rotations,
                active_step_index=k,
                gait_phase=u % 1.0,
                is_flight=is_flight,
            )

            bridge_res = bridge_executor.execute_frame(planned_pose, keyframe=True, dt=1.0 / fps)

            eff_l = bridge_res.wbc_result.end_effectors.get("foot_L")
            eff_r = bridge_res.wbc_result.end_effectors.get("foot_R")

            if eff_l and (not eff_l.is_reachable or not eff_l.strictly_in_reach):
                unreachable.append({
                    "frame": frame,
                    "side": "L",
                    "phase": ph_l,
                    "dist": round(eff_l.reach_distance_m, 5),
                })
            if eff_r and (not eff_r.is_reachable or not eff_r.strictly_in_reach):
                unreachable.append({
                    "frame": frame,
                    "side": "R",
                    "phase": ph_r,
                    "dist": round(eff_r.reach_distance_m, 5),
                })

            if not bridge_res.success:
                for uc in bridge_res.unmet_constraints:
                    unreachable.append({
                        "frame": frame,
                        "category": uc.category,
                        "target": uc.target_name,
                        "error": uc.error_amount,
                        "desc": uc.description,
                    })

            raw_l = {
                "target_world": eff_l.requested_world_xyz if eff_l else (0.0, 0.0, 0.0),
                "actual_world": eff_l.actual_world_xyz if eff_l else (0.0, 0.0, 0.0),
                "is_reachable": eff_l.is_reachable if eff_l else True,
                "strictly_in_reach": eff_l.strictly_in_reach if eff_l else True,
                "hip_to_target_dist": eff_l.reach_distance_m if eff_l else 0.0,
                "position_error_m": eff_l.position_error_m if eff_l else 0.0,
            }
            raw_r = {
                "target_world": eff_r.requested_world_xyz if eff_r else (0.0, 0.0, 0.0),
                "actual_world": eff_r.actual_world_xyz if eff_r else (0.0, 0.0, 0.0),
                "is_reachable": eff_r.is_reachable if eff_r else True,
                "strictly_in_reach": eff_r.strictly_in_reach if eff_r else True,
                "hip_to_target_dist": eff_r.reach_distance_m if eff_r else 0.0,
                "position_error_m": eff_r.position_error_m if eff_r else 0.0,
            }

            ms = bridge_res.motion_state
            ms_params = dict(ms.params)
            ms_params.update({
                "tau": tau,
                "stage": stage,
                "step_k": k,
                "local_f": local,
                "cycle_phase": phase_name,
                "psi": round(psi, 4),
                "pelvis_dz": round(dz, 5),
                "torso_pitch_deg": round(-(pelvis_rx + spine_rx), 3),
                "arm_l_rx": round(arm_l, 2),
                "arm_r_rx": round(arm_r, 2),
            })
            ms = ms.clone_with(params=ms_params)
            states.append(ms)

            records.append({
                "frame": frame,
                "tau": tau,
                "stage": stage,
                "mode": mode.value,
                "step_k": k,
                "local_f": local,
                "cycle_phase": phase_name,
                "is_airborne": is_flight,
                "root_y": round(root_y, 5),
                "speed_mps": round(speed, 5),
                "accel_mps2": round(accel, 5),
                "pelvis_dz": round(dz, 5),
                "torso_pitch_deg": round(-(pelvis_rx + spine_rx), 3),
                "arm_l_rx": round(arm_l, 2),
                "arm_r_rx": round(arm_r, 2),
                "phase_l": ph_l,
                "phase_r": ph_r,
                "state_l": raw_l,
                "state_r": raw_r,
            })

        if clamp_events:
            raise RuntimeError(f"IK target was clamped {len(clamp_events)} times (contact faking): {clamp_events[:5]}")
        if unreachable:
            raise RuntimeError(f"{len(unreachable)} IK reach violations during SprintStartAction: {unreachable[:5]}")

        used_steps = [s for s in steps if s["tau_start"] < total]
        return ActionExecutionResult(
            action_name=self.name,
            initial_state=initial_state,
            final_state=states[-1],
            states=states,
            frame_records=records,
            step_schedule=used_steps,
            unreachable_count=len(unreachable),
            metrics={
                "total_frames": total,
                "fps": config.fps,
                "peak_speed_mps": round(max(r["speed_mps"] for r in records), 5),
                "final_speed_mps": round(records[-1]["speed_mps"], 5),
                "total_root_displacement": round(records[-1]["root_y"] - records[0]["root_y"], 5),
                "airborne_frames_total": sum(1 for r in records if r["is_airborne"]),
                "clamp_events": 0,
            },
        )


def run_task6c_via_motion_framework(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
) -> Dict[str, Any]:
    planner = MotionPlanner(config, armature_obj=armature_obj)
    planner.add_action(SprintStartAction())
    return planner.execute()
