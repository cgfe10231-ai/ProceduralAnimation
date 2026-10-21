"""Active braking and sudden stop (`SprintBrakeAction`) in the unified motion framework (Task 6D).

Sequence: steady sprint handoff -> active deceleration reaction -> continuous braking steps
-> final settling -> stationary standing.

Design:
- Fully integrated with the Task 6A unified motion framework (`MotionState`, `MotionAction`, `MotionPlanner`),
  reusing `ContactConstraintAdapter`, `BlenderPoseApplicator`, two-bone leg IK, and Task 6B swing trajectory.
- Seamlessly inherits terminal momentum from Task 6C (`SprintStartAction`):
  root position, forward velocity (2.0 m/s), torso lean, pelvis cushion, and foot contacts.
- Root kinematics:
  Cos-tapered monotonic deceleration profile v(x) = (v0 / 2) * (1 + cos(pi * x)), x in [0, 1].
  Zero initial jerk, strictly monotonic speed decline, exact zero final velocity and zero acceleration.
  Total braking displacement D_brake = (v0 * T_brake) / (2 * fps).
- Adaptive braking footwork:
  - Step 0 (Continuation): Right foot holds locked world position from handoff while Left foot completes swing.
  - Step 1 (Primary Brake Plant): Left foot plants ahead at y_l1 = sy + (4/9)*D_brake; absorbs primary inertia.
  - Step 2 (Secondary Brake Plant): Right foot swings and plants at y_r1 = sy + (7/9)*D_brake.
  - Step 3 (Final Settle Step): Left foot swings and plants symmetrically at y_l2 = sy + D_brake.
  - Step 4 (Closing Step): Right foot closes up to y_r2 = sy + D_brake.
  - Dual-stance hold: Both feet firmly planted at y_final with zero drift and zero jitter.
- Biomechanical braking posture:
  - Deep knee cushioning (pelvis drops to -0.115 m) during peak deceleration, then recovers to neutral rest (-0.01 m).
  - Torso smoothly pitches from forward sprint lean (+15.09°) back to slight backward lean (-6.0°) to counter
    forward momentum, then gently recovers to upright (0.0°).
  - Contralateral arm swing damps down with velocity, settling into relaxed standing posture.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

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


def evaluate_brake_root_kinematics(
    step_idx: int,
    v0: float,
    t_brake: int,
    fps: float,
) -> Tuple[float, float, float]:
    """Return `(root_disp_m, speed_mps, accel_mps2)` at discrete frame index `step_idx`.

    - `step_idx = 0` corresponds to the handoff instant (v = v0, disp = 0).
    - `step_idx = 1` corresponds to the first timeline frame of the action (frame 115).
    - `step_idx >= t_brake` yields exactly zero velocity and zero acceleration.
    """
    if step_idx <= 0:
        return 0.0, v0, 0.0
    if step_idx <= t_brake:
        x = step_idx / float(t_brake)
        speed = 0.5 * v0 * (1.0 + math.cos(math.pi * x))
        accel = -0.5 * v0 * (math.pi / (t_brake / fps)) * math.sin(math.pi * x)
        disp = (0.5 * v0 / fps) * (step_idx + (t_brake / math.pi) * math.sin(math.pi * x))
    else:
        speed = 0.0
        accel = 0.0
        disp = (0.5 * v0 / fps) * t_brake
    return disp, speed, accel


def apply_brake_pose(
    arm: bpy.types.Object,
    config: PipelineConfig,
    tau: int,
    t_brake: int,
    t_total: int,
    speed_mps: float,
    v0: float,
) -> Tuple[float, float, float, float]:
    """Apply biomechanical braking posture: pelvis cushion/rebound, torso inertial counter-lean, and arm settling.

    Returns `(pelvis_dz, torso_pitch_deg, arm_l_rx, arm_r_rx)`.
    """
    x_total = min(1.0, tau / float(t_total))

    # Pelvis cushion and rebound
    if tau <= 14:
        crouch = _lerp(-0.08038, -0.115, _smoothstep01(tau / 14.0))
    else:
        crouch = _lerp(-0.115, -0.010, _smoothstep01((tau - 14.0) / (t_total - 14.0)))

    # Torso pitch: smoothly swings from forward sprint lean (+15.091 deg) to slight backward lean (-6.0 deg)
    # to absorb forward momentum, then smoothly returns to upright (0.0 deg)
    if tau <= 14:
        torso_pitch = _lerp(15.091, -6.0, _smoothstep01(tau / 14.0))
    elif tau <= t_brake:
        torso_pitch = _lerp(-6.0, 0.0, _smoothstep01((tau - 14.0) / (t_brake - 14.0)))
    else:
        torso_pitch = 0.0

    speed_factor = max(0.0, speed_mps / v0) if v0 > 1e-4 else 0.0

    pelvis_dz = crouch
    set_bone_location(arm, "pelvis", (0.0, pelvis_dz, 0.0), update=False)

    pelvis_rx = -0.3 * torso_pitch
    set_bone_rotation(arm, "pelvis", (pelvis_rx, 0.0, 0.0), update=False)

    spine_rx = -0.7 * torso_pitch
    set_bone_rotation(arm, "spine", (spine_rx, 0.0, 0.0), update=False)

    for bone in ("neck", "head"):
        set_bone_rotation(arm, bone, (0.5 * torso_pitch, 0.0, 0.0), update=False)

    # Arms: contralateral swing damps with speed, settling into neutral rest
    arm_swing = 18.0 * speed_factor * math.cos(math.pi * tau / 10.0)
    arm_l = arm_swing
    arm_r = -arm_swing
    elbow = _lerp(config.run_elbow_base_deg, 10.0, _smoothstep01(x_total))

    set_bone_rotation(arm, "upper_arm.L", (arm_l, 0.0, -5.0), update=False)
    set_bone_rotation(arm, "forearm.L", (elbow, 0.0, 0.0), update=False)
    set_bone_rotation(arm, "upper_arm.R", (arm_r, 0.0, 5.0), update=False)
    set_bone_rotation(arm, "forearm.R", (elbow, 0.0, 0.0), update=True)

    return pelvis_dz, torso_pitch, arm_l, arm_r


class SprintBrakeAction(MotionAction):
    """Active braking and sudden stop action following a high-speed sprint.

    Decelerates root from sprint speed (2.0 m/s) to 0.0 m/s via parametric braking steps,
    settling the character into a stable bilateral standing pose.
    """

    @property
    def name(self) -> str:
        return "sprint_brake"

    def can_start_from(self, state: MotionState) -> bool:
        return state.mode == MotionMode.SPRINT and state.velocity[1] > 0.5

    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
        _ = initial_state
        return config.sprint_brake_total_frames

    def execute(self, initial_state: MotionState, context: MotionRuntimeContext) -> ActionExecutionResult:
        if not self.can_start_from(initial_state):
            raise ValueError(
                f"SprintBrakeAction requires SPRINT mode with forward velocity > 0.5 m/s, "
                f"got mode={initial_state.mode}, velocity={initial_state.velocity}"
            )

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

        t_brake = config.sprint_brake_frames
        t_total = config.sprint_brake_total_frames
        v0 = initial_state.velocity[1]

        start_frame = initial_state.frame
        sx, sy, _ = initial_state.position
        yaw = initial_state.yaw_deg
        fx, fy, _ = forward_unit_vector_from_yaw(yaw)
        x_of = {"L": sx - HIP_X_OFFSET, "R": sx + HIP_X_OFFSET}

        total_disp = (0.5 * v0 / fps) * t_brake
        final_y = sy + total_disp

        init_r_pos = initial_state.contacts["foot_R"].current_world_xyz
        init_l_pos = initial_state.contacts["foot_L"].current_world_xyz

        y_r0 = init_r_pos[1]
        y_l1 = sy + (4.0 / 9.0) * total_disp
        y_r1 = sy + (7.0 / 9.0) * total_disp
        y_l2 = final_y
        y_r2 = final_y

        clamp_events: List[dict] = []
        unreachable: List[dict] = []
        states: List[MotionState] = []
        records: List[dict] = []

        for tau in range(t_total):
            frame = start_frame + tau
            scene.frame_set(frame)

            step_idx = tau + 1
            disp, speed, accel = evaluate_brake_root_kinematics(step_idx, v0, t_brake, fps)
            root_y = sy + disp
            root_world = (sx, root_y, env.ground_height_at(sx, root_y))

            x_total = min(1.0, tau / float(t_total))
            if tau <= 14:
                crouch = _lerp(-0.08038, -0.115, _smoothstep01(tau / 14.0))
                torso_pitch = _lerp(15.091, -6.0, _smoothstep01(tau / 14.0))
            elif tau <= t_brake:
                crouch = _lerp(-0.115, -0.010, _smoothstep01((tau - 14.0) / (t_total - 14.0)))
                torso_pitch = _lerp(-6.0, 0.0, _smoothstep01((tau - 14.0) / (t_brake - 14.0)))
            else:
                crouch = _lerp(-0.115, -0.010, _smoothstep01((tau - 14.0) / (t_total - 14.0)))
                torso_pitch = 0.0

            speed_factor = max(0.0, speed / v0) if v0 > 1e-4 else 0.0

            pelvis_dz = crouch
            pelvis_loc = (0.0, pelvis_dz, 0.0)
            pelvis_rx = -0.3 * torso_pitch
            spine_rx = -0.7 * torso_pitch
            neck_rot = (0.5 * torso_pitch, 0.0, 0.0)
            head_rot = (0.5 * torso_pitch, 0.0, 0.0)

            arm_swing = 18.0 * speed_factor * math.cos(math.pi * tau / 10.0)
            arm_l = arm_swing
            arm_r = -arm_swing
            elbow = _lerp(config.run_elbow_base_deg, 10.0, _smoothstep01(x_total))

            fk_rotations = {
                "upper_arm.L": (arm_l, 0.0, -5.0),
                "forearm.L": (elbow, 0.0, 0.0),
                "upper_arm.R": (arm_r, 0.0, 5.0),
                "forearm.R": (elbow, 0.0, 0.0),
            }

            # Foot contact schedule
            if tau < 3:
                zg_r = env.ground_height_at(x_of["R"], y_r0)
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(x_of["R"], y_r0, zg_r + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                s_l = (tau + 8) / 11.0
                y_l, lift_l = compute_run_swing_point(init_l_pos[1] - 0.77, y_l1, s_l, 0.10)
                pitch_l = -12.0 * math.sin(math.pi * max(0.0, min(1.0, s_l)))
                zg_l = env.ground_height_at(x_of["L"], y_l)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(x_of["L"], y_l, zg_l + ANKLE_REST_Z + lift_l),
                    is_locked=False,
                    rotation_deg=(pitch_l, 0.0, yaw),
                    contact_intent=False,
                )
                ph_r, ph_l = "stance", "swing"
            elif tau < 12:
                zg_l = env.ground_height_at(x_of["L"], y_l1)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(x_of["L"], y_l1, zg_l + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                s_r = (tau - 3) / 9.0
                y_r, lift_r = compute_run_swing_point(y_r0, y_r1, s_r, 0.08)
                pitch_r = -12.0 * math.sin(math.pi * max(0.0, min(1.0, s_r)))
                zg_r = env.ground_height_at(x_of["R"], y_r)
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(x_of["R"], y_r, zg_r + ANKLE_REST_Z + lift_r),
                    is_locked=False,
                    rotation_deg=(pitch_r, 0.0, yaw),
                    contact_intent=False,
                )
                ph_l, ph_r = "stance", "swing"
            elif tau < 24:
                zg_r = env.ground_height_at(x_of["R"], y_r1)
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(x_of["R"], y_r1, zg_r + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                s_l = (tau - 12) / 12.0
                y_l, lift_l = compute_run_swing_point(y_l1, y_l2, s_l, 0.06)
                pitch_l = -12.0 * math.sin(math.pi * max(0.0, min(1.0, s_l)))
                zg_l = env.ground_height_at(x_of["L"], y_l)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(x_of["L"], y_l, zg_l + ANKLE_REST_Z + lift_l),
                    is_locked=False,
                    rotation_deg=(pitch_l, 0.0, yaw),
                    contact_intent=False,
                )
                ph_r, ph_l = "stance", "swing"
            elif tau < 34:
                zg_l = env.ground_height_at(x_of["L"], y_l2)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(x_of["L"], y_l2, zg_l + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                s_r = (tau - 24) / 10.0
                y_r, lift_r = compute_run_swing_point(y_r1, y_r2, s_r, 0.04)
                pitch_r = -12.0 * math.sin(math.pi * max(0.0, min(1.0, s_r)))
                zg_r = env.ground_height_at(x_of["R"], y_r)
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(x_of["R"], y_r, zg_r + ANKLE_REST_Z + lift_r),
                    is_locked=False,
                    rotation_deg=(pitch_r, 0.0, yaw),
                    contact_intent=False,
                )
                ph_l, ph_r = "stance", "swing"
            else:
                zg_r = env.ground_height_at(x_of["R"], y_r2)
                zg_l = env.ground_height_at(x_of["L"], y_l2)
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(x_of["R"], y_r2, zg_r + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(x_of["L"], y_l2, zg_l + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw),
                    contact_intent=True,
                )
                ph_l = ph_r = "stance"

            stage = "brake" if tau < t_brake else "stop"
            mode = MotionMode.DECELERATE if tau < t_brake else MotionMode.STOP
            gait_phase = 0.0 if stage == "stop" else ((tau / float(t_brake)) % 1.0)

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
                pelvis_rotation_deg=(pelvis_rx, 0.0, 0.0),
                spine_rotation_deg=(spine_rx, 0.0, 0.0),
                neck_rotation_deg=neck_rot,
                head_rotation_deg=head_rot,
                foot_L=foot_tgt_l,
                foot_R=foot_tgt_r,
                hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
                hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
                fk_joint_rotations_deg=fk_rotations,
                active_step_index=0,
                gait_phase=gait_phase,
                is_flight=False,
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
                "speed": round(speed, 5),
                "pelvis_dz": round(pelvis_dz, 5),
                "torso_pitch_deg": round(torso_pitch, 3),
            })
            ms = ms.clone_with(params=ms_params)
            states.append(ms)

            records.append({
                "frame": frame,
                "tau": tau,
                "stage": stage,
                "mode": mode.value,
                "root_y": round(root_y, 5),
                "speed_mps": round(speed, 5),
                "accel_mps2": round(accel, 5),
                "pelvis_dz": round(pelvis_dz, 5),
                "torso_pitch_deg": round(torso_pitch, 3),
                "phase_l": ph_l,
                "phase_r": ph_r,
                "state_l": raw_l,
                "state_r": raw_r,
            })

        if clamp_events:
            raise RuntimeError(f"IK target was clamped {len(clamp_events)} times during braking: {clamp_events[:5]}")
        if unreachable:
            raise RuntimeError(f"{len(unreachable)} IK reach violations during SprintBrakeAction: {unreachable[:5]}")

        return ActionExecutionResult(
            action_name=self.name,
            initial_state=initial_state,
            final_state=states[-1],
            states=states,
            frame_records=records,
            unreachable_count=0,
            metrics={
                "total_frames": t_total,
                "brake_frames": t_brake,
                "settle_frames": config.sprint_settle_frames,
                "fps": config.fps,
                "initial_speed_mps": round(v0, 5),
                "final_speed_mps": round(records[-1]["speed_mps"], 5),
                "total_brake_displacement": round(records[-1]["root_y"] - sy, 5),
                "max_deceleration_mps2": round(min(r["accel_mps2"] for r in records), 5),
                "clamp_events": 0,
                "unreachable_count": 0,
            },
        )


def run_task6d_via_motion_framework(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
    include_sprint_start: bool = True,
) -> Dict[str, Any]:
    """Execute the chained sprint start and active braking prototype via `MotionPlanner`."""
    planner = MotionPlanner(config, armature_obj=armature_obj)
    if include_sprint_start:
        from src.motion.sprint_start import SprintStartAction
        planner.add_action(SprintStartAction())
    planner.add_action(SprintBrakeAction())
    return planner.execute()
