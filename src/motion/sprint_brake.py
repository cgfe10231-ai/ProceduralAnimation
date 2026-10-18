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
        adapter = context.contact_adapter
        pose = context.pose_applicator
        arm = context.armature_obj
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

        def set_swing(side: str, y_from: float, y_to: float, s: float, hgt: float, frame: int):
            y, lift = compute_run_swing_point(y_from, y_to, s, hgt)
            zg = env.ground_height_at(x_of[side], y)
            req = (x_of[side], y, zg + ANKLE_REST_Z + lift)
            raw, cp = adapter.set_swing_foot_target(side, req, foot_rotation_deg=(0.0, 0.0, yaw))
            applied = bpy.data.objects[IK_TARGET_NAMES[side]].matrix_world.translation
            err = max(abs(applied[i] - req[i]) for i in range(3))
            if err > 1e-4:
                clamp_events.append({"frame": frame, "side": side, "err": round(err, 5)})
            return raw, cp

        for tau in range(t_total):
            frame = start_frame + tau
            scene.frame_set(frame)

            step_idx = tau + 1
            disp, speed, accel = evaluate_brake_root_kinematics(step_idx, v0, t_brake, fps)
            root_y = sy + disp
            root_world = (sx, root_y, env.ground_height_at(sx, root_y))

            adapter.move_root_preserving_locks(root_world)
            pelvis_dz, torso_pitch, arm_l, arm_r = apply_brake_pose(
                arm, config, tau, t_brake, t_total, speed, v0
            )

            # Foot contact schedule:
            # tau < 3: R stance (holding from 6C), L swinging to land at tau=3
            # tau in [3, 12): L stance at y_l1, R swinging to land at tau=12
            # tau in [12, 24): R stance at y_r1, L swinging to land at tau=24
            # tau in [24, 34): L stance at y_l2, R swinging to land at tau=34
            # tau >= 34: Both feet locked at final_y in stable bilateral stance
            if tau < 3:
                if tau == 0:
                    raw_r, cp_r = adapter.lock_foot(
                        "R",
                        (x_of["R"], y_r0, env.ground_height_at(x_of["R"], y_r0)),
                        (0.0, 0.0, yaw),
                    )
                else:
                    raw_r, cp_r = adapter.evaluate_locked_foot("R")
                ph_r = "stance"

                s_l = (tau + 8) / 11.0
                raw_l, cp_l = set_swing("L", init_l_pos[1] - 0.77, y_l1, s_l, 0.10, frame)
                ph_l = "swing"
            elif tau < 12:
                if tau == 3:
                    raw_l, cp_l = adapter.lock_foot(
                        "L",
                        (x_of["L"], y_l1, env.ground_height_at(x_of["L"], y_l1)),
                        (0.0, 0.0, yaw),
                    )
                else:
                    raw_l, cp_l = adapter.evaluate_locked_foot("L")
                ph_l = "stance"

                s_r = (tau - 3) / 9.0
                raw_r, cp_r = set_swing("R", y_r0, y_r1, s_r, 0.08, frame)
                ph_r = "swing"
            elif tau < 24:
                if tau == 12:
                    raw_r, cp_r = adapter.lock_foot(
                        "R",
                        (x_of["R"], y_r1, env.ground_height_at(x_of["R"], y_r1)),
                        (0.0, 0.0, yaw),
                    )
                else:
                    raw_r, cp_r = adapter.evaluate_locked_foot("R")
                ph_r = "stance"

                s_l = (tau - 12) / 12.0
                raw_l, cp_l = set_swing("L", y_l1, y_l2, s_l, 0.06, frame)
                ph_l = "swing"
            elif tau < 34:
                if tau == 24:
                    raw_l, cp_l = adapter.lock_foot(
                        "L",
                        (x_of["L"], y_l2, env.ground_height_at(x_of["L"], y_l2)),
                        (0.0, 0.0, yaw),
                    )
                else:
                    raw_l, cp_l = adapter.evaluate_locked_foot("L")
                ph_l = "stance"

                s_r = (tau - 24) / 10.0
                raw_r, cp_r = set_swing("R", y_r1, y_r2, s_r, 0.04, frame)
                ph_r = "swing"
            else:
                if tau == 34:
                    raw_r, cp_r = adapter.lock_foot(
                        "R",
                        (x_of["R"], y_r2, env.ground_height_at(x_of["R"], y_r2)),
                        (0.0, 0.0, yaw),
                    )
                else:
                    raw_r, cp_r = adapter.evaluate_locked_foot("R")
                raw_l, cp_l = adapter.evaluate_locked_foot("L")
                ph_l = ph_r = "stance"

            for side, raw, ph in (("L", raw_l, ph_l), ("R", raw_r, ph_r)):
                if not raw["is_reachable"] or not raw["strictly_in_reach"]:
                    unreachable.append({
                        "frame": frame,
                        "side": side,
                        "phase": ph,
                        "dist": round(raw["hip_to_target_dist"], 5),
                    })

            pose.keyframe_current_frame(frame)

            stage = "brake" if tau < t_brake else "stop"
            mode = MotionMode.DECELERATE if tau < t_brake else MotionMode.STOP
            airborne = not (cp_l.is_locked or cp_r.is_locked)

            ms = MotionState(
                frame=frame,
                time_sec=(frame - 1) / fps,
                position=root_world,
                orientation_deg=initial_state.orientation_deg,
                velocity=(fx * speed, fy * speed, 0.0),
                acceleration=(fx * accel, fy * accel, 0.0),
                mode=mode,
                gait_phase=0.0 if stage == "stop" else ((tau / float(t_brake)) % 1.0),
                contacts={"foot_L": cp_l, "foot_R": cp_r},
                is_airborne=airborne,
                params={
                    "tau": tau,
                    "stage": stage,
                    "speed": round(speed, 5),
                    "pelvis_dz": round(pelvis_dz, 5),
                    "torso_pitch_deg": round(torso_pitch, 3),
                },
            )
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
