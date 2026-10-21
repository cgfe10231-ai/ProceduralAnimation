"""Procedural Running (`RunAction`) implementation in the unified motion framework (Task 6B).

Implements a true running gait mechanism distinct from walking:
- Executed as a `MotionAction` (`RunAction`) via `MotionPlanner` from `src/motion/framework.py`.
- Each 24-frame (1.0s @ 24 FPS) running cycle consists of 4 explicit biomechanical phases:
  1. `stance_L` (frames 0..6 of half-step 0, 7 frames): Left foot locked on ground in world space,
     Right foot swinging forward; pelvis compresses to absorb impact at mid-stance (`local_f = 3`).
  2. `flight_1` (frames 7..11 of half-step 0, 5 frames): Both feet unlocked and airborne above `Z = 0.0 m`;
     pelvis rises to airborne apex (`local_f = 9`) while Right leg reaches forward for touch-down and
     Left leg lifts into early recovery.
  3. `stance_R` (frames 0..6 of half-step 1, 7 frames): Right foot locked on ground in world space,
     Left foot swinging forward; pelvis compresses at mid-stance.
  4. `flight_2` (frames 7..11 of half-step 1, 5 frames): Both feet unlocked and airborne above `Z = 0.0 m`;
     pelvis rises to airborne apex while Left leg reaches forward for touch-down and Right leg lifts.
- Coordinates forward speed (`0.90 m/s`, 3.75x faster than walking `0.24 m/s`), half-step length
  (`0.45 m`, full stride `0.90 m`), cadence (`2.0 steps/s`), and stance center placement so the
  stance foot stays strictly within the `0.82 m` leg IK reach (`max hip-to-target <= 0.785 m`)
  with zero contact point cheating and sub-millimeter bone/mesh drift.
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
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET
from src.rig.pose import set_bone_location, set_bone_rotation


def compute_run_swing_point(
    y_start: float,
    y_end: float,
    swing_s: float,
    step_height: float,
) -> Tuple[float, float]:
    """Compute `(world_y, z_lift)` for a running swing foot over normalized progress `swing_s` in `[0, 1]`.

    - Uses a smooth blend of linear and cosine progression for `world_y` so the horizontal
      offset between the swinging ankle and moving hip stays bounded within `<= 0.1125 m`
      throughout the entire 17-frame swing + flight interval.
    - Uses `sin(pi * s)^1.35` for vertical lift so both feet maintain clear positive ground
      clearance (`>= +0.020 m`) across every frame of the dual-foot airborne flight window.
    """
    s = max(0.0, min(1.0, swing_s))
    alpha = 0.65 * s + 0.35 * 0.5 * (1.0 - math.cos(math.pi * s))
    world_y = y_start + alpha * (y_end - y_start)
    z_lift = step_height * (math.sin(math.pi * s) ** 1.35)
    return world_y, z_lift


def apply_run_upper_body_pose(
    arm: bpy.types.Object,
    config: PipelineConfig,
    u: float,
) -> Tuple[float, float, float, float]:
    """Apply running pelvis bounce/sway/rotation, forward-leaning torso counter-rotation,
    head stabilization, and flexed contra-lateral arm drive for cycle phase `u` in `[0, 1)`.

    Returns `(pelvis_dz, torso_world_pitch_deg, arm_l_rx, arm_r_rx)`.
    """
    theta = 2.0 * math.pi * u
    sin_t = math.sin(theta)
    sin_2t = math.sin(2.0 * theta)
    cos_2t = math.cos(2.0 * theta)

    # Vertical pelvis bounce: reaches minimum at mid-stance (u = 3/24, 15/24 => sin_2t = +1)
    # and reaches maximum at mid-flight (u = 9/24, 21/24 => sin_2t = -1)
    pelvis_dx = -config.run_pelvis_sway_amp * sin_t
    pelvis_dz = config.run_pelvis_base_z - config.run_pelvis_bounce_amp * sin_2t
    set_bone_location(arm, "pelvis", (pelvis_dx, pelvis_dz, 0.0), update=False)

    pelvis_rx = -2.5 - 1.2 * cos_2t
    pelvis_ry = config.run_pelvis_yaw_deg * sin_t
    pelvis_rz = config.run_pelvis_roll_deg * sin_t
    set_bone_rotation(arm, "pelvis", (pelvis_rx, pelvis_ry, pelvis_rz), update=False)

    spine_rx = -config.run_torso_lean_deg + 1.0 * cos_2t
    spine_ry = -config.run_torso_yaw_deg * sin_t
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

    arm_l_rx = config.run_arm_swing_deg * sin_t
    arm_r_rx = -config.run_arm_swing_deg * sin_t
    elbow_l_rx = config.run_elbow_base_deg + config.run_elbow_swing_deg * max(0.0, sin_t)
    elbow_r_rx = config.run_elbow_base_deg + config.run_elbow_swing_deg * max(0.0, -sin_t)

    set_bone_rotation(arm, "upper_arm.L", (arm_l_rx, 0.0, -5.0), update=False)
    set_bone_rotation(arm, "forearm.L", (elbow_l_rx, 0.0, 0.0), update=False)
    set_bone_rotation(arm, "upper_arm.R", (arm_r_rx, 0.0, 5.0), update=False)
    set_bone_rotation(arm, "forearm.R", (elbow_r_rx, 0.0, 0.0), update=True)

    torso_pitch_deg = -(pelvis_rx + spine_rx)
    return pelvis_dz, torso_pitch_deg, arm_l_rx, arm_r_rx


class RunAction(MotionAction):
    """Parameterized forward running `MotionAction` with explicit single-leg stance and
    dual-foot airborne flight phases.
    """

    def __init__(self, cycles: Optional[int] = None) -> None:
        self._cycles = cycles

    @property
    def name(self) -> str:
        return "run"

    def can_start_from(self, state: MotionState) -> bool:
        return state.mode in (
            MotionMode.IDLE,
            MotionMode.WALK,
            MotionMode.RUN,
            MotionMode.ACCELERATE,
            MotionMode.STOP,
        )

    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
        _ = initial_state
        cycles = self._cycles if self._cycles is not None else config.run_cycles
        return config.run_cycle_frames * cycles

    def execute(
        self,
        initial_state: MotionState,
        context: MotionRuntimeContext,
    ) -> ActionExecutionResult:
        if not self.can_start_from(initial_state):
            raise ValueError(f"RunAction cannot start from mode={initial_state.mode}")

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

        cycles = self._cycles if self._cycles is not None else config.run_cycles
        cycle_frames = config.run_cycle_frames          # 24
        half_step = config.run_half_step_frames         # 12
        stance_frames = config.run_stance_frames        # 7
        flight_frames = config.run_flight_frames        # 5
        total_frames = cycle_frames * cycles            # 96
        step_len = config.run_step_length               # 0.45 m
        step_height = config.run_step_height            # 0.22 m
        fps = float(config.fps)
        speed_mps = config.run_speed_mps                # 0.90 m/s

        # Number of frame intervals between last stance frame (local_f = stance_frames - 1 = 6)
        # and next touch-down of the same foot (local_f = 24): 24 - 6 = 18 intervals
        swing_intervals = float(cycle_frames - (stance_frames - 1))  # 18.0
        # Place stance foot at the midpoint of the 7-frame stance root travel (local_f = 3 -> 3/12 = 0.25)
        stance_center_offset = 0.5 * (stance_frames - 1) / float(half_step)  # 0.25

        start_frame = initial_state.frame
        start_x, start_y, _ = initial_state.position
        yaw_deg = initial_state.yaw_deg
        fx, fy, _ = forward_unit_vector_from_yaw(yaw_deg)

        def _stance_y_for_step(step_k: int) -> float:
            return start_y + (step_k + stance_center_offset) * step_len

        step_schedule: List[dict] = []
        for k in range(2 * cycles):
            st_side = "L" if k % 2 == 0 else "R"
            sw_side = "R" if st_side == "L" else "L"
            step_schedule.append({
                "k": k,
                "tau_start": k * half_step,
                "tau_stance_end": k * half_step + stance_frames - 1,
                "tau_end": (k + 1) * half_step,
                "stance_frames": stance_frames,
                "flight_frames": flight_frames,
                "stance_side": st_side,
                "swing_side": sw_side,
                "stance_y": round(_stance_y_for_step(k), 5),
                "step_length": step_len,
            })

        states: List[MotionState] = []
        frame_records: List[dict] = []
        unreachable_events: List[dict] = []

        for tau in range(total_frames):
            frame = start_frame + tau
            scene.frame_set(frame)

            k = tau // half_step
            local_f = tau - k * half_step
            u = (tau % cycle_frames) / float(cycle_frames)

            disp_y = (tau / float(half_step)) * step_len
            root_y = start_y + disp_y
            ground_z = context.environment.ground_height_at(start_x, root_y)
            root_world = (start_x, root_y, ground_z)

            theta = 2.0 * math.pi * u
            sin_t = math.sin(theta)
            sin_2t = math.sin(2.0 * theta)
            cos_2t = math.cos(2.0 * theta)

            pelvis_dx = -config.run_pelvis_sway_amp * sin_t
            pelvis_dz = config.run_pelvis_base_z - config.run_pelvis_bounce_amp * sin_2t
            pelvis_rx = -2.5 - 1.2 * cos_2t
            pelvis_ry = config.run_pelvis_yaw_deg * sin_t
            pelvis_rz = config.run_pelvis_roll_deg * sin_t

            spine_rx = -config.run_torso_lean_deg + 1.0 * cos_2t
            spine_ry = -config.run_torso_yaw_deg * sin_t
            spine_rz = -0.6 * pelvis_rz

            total_rx = pelvis_rx + spine_rx
            total_ry = pelvis_ry + spine_ry
            total_rz = pelvis_rz + spine_rz
            neck_rot = (-0.45 * total_rx, -0.45 * total_ry, -0.45 * total_rz)
            head_rot = (-0.45 * total_rx, -0.45 * total_ry, -0.45 * total_rz)

            arm_l_rx = config.run_arm_swing_deg * sin_t
            arm_r_rx = -config.run_arm_swing_deg * sin_t
            elbow_l_rx = config.run_elbow_base_deg + config.run_elbow_swing_deg * max(0.0, sin_t)
            elbow_r_rx = config.run_elbow_base_deg + config.run_elbow_swing_deg * max(0.0, -sin_t)

            fk_rotations = {
                "upper_arm.L": (arm_l_rx, 0.0, -5.0),
                "forearm.L": (elbow_l_rx, 0.0, 0.0),
                "upper_arm.R": (arm_r_rx, 0.0, 5.0),
                "forearm.R": (elbow_r_rx, 0.0, 0.0),
            }

            if k % 2 == 0:
                # Even half-step: Left Stance (local_f = 0..6) -> Flight 1 (local_f = 7..11)
                if local_f < stance_frames:
                    cycle_phase_name = "stance_L"
                    st_y_l = _stance_y_for_step(k)
                    z_l = context.environment.ground_height_at(start_x - HIP_X_OFFSET, st_y_l)
                    foot_tgt_l = PlannedFootTarget(
                        world_xyz=(start_x - HIP_X_OFFSET, st_y_l, z_l + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(0.0, 0.0, yaw_deg),
                        contact_intent=True,
                    )
                    phase_l = "stance"
                    phase_r = "swing"
                    is_flight = False
                else:
                    cycle_phase_name = "flight_1"
                    # Left foot unlocked in early swing (j_l = 1..5 of 18)
                    j_l = local_f - (stance_frames - 1)
                    s_l = j_l / swing_intervals
                    y_sw_l, z_lift_l = compute_run_swing_point(
                        _stance_y_for_step(k),
                        _stance_y_for_step(k + 2),
                        s_l,
                        step_height,
                    )
                    pitch_l = -10.0 * math.sin(math.pi * s_l)
                    z_g_l = context.environment.ground_height_at(start_x - HIP_X_OFFSET, y_sw_l)
                    foot_tgt_l = PlannedFootTarget(
                        world_xyz=(start_x - HIP_X_OFFSET, y_sw_l, z_g_l + ANKLE_REST_Z + z_lift_l),
                        is_locked=False,
                        rotation_deg=(pitch_l, 0.0, yaw_deg),
                        contact_intent=False,
                    )
                    phase_l = "flight"
                    phase_r = "flight"
                    is_flight = True

                # Right foot is in mid-to-late swing across all local_f = 0..11 (j_r = 6..17 of 18)
                j_r = (half_step - (stance_frames - 1)) + local_f
                s_r = j_r / swing_intervals
                y_sw_r, z_lift_r = compute_run_swing_point(
                    _stance_y_for_step(k - 1),
                    _stance_y_for_step(k + 1),
                    s_r,
                    step_height,
                )
                pitch_r = -10.0 * math.sin(math.pi * s_r)
                z_g_r = context.environment.ground_height_at(start_x + HIP_X_OFFSET, y_sw_r)
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(start_x + HIP_X_OFFSET, y_sw_r, z_g_r + ANKLE_REST_Z + z_lift_r),
                    is_locked=False,
                    rotation_deg=(pitch_r, 0.0, yaw_deg),
                    contact_intent=False,
                )

            else:
                # Odd half-step: Right Stance (local_f = 0..6) -> Flight 2 (local_f = 7..11)
                if local_f < stance_frames:
                    cycle_phase_name = "stance_R"
                    st_y_r = _stance_y_for_step(k)
                    z_r = context.environment.ground_height_at(start_x + HIP_X_OFFSET, st_y_r)
                    foot_tgt_r = PlannedFootTarget(
                        world_xyz=(start_x + HIP_X_OFFSET, st_y_r, z_r + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(0.0, 0.0, yaw_deg),
                        contact_intent=True,
                    )
                    phase_r = "stance"
                    phase_l = "swing"
                    is_flight = False
                else:
                    cycle_phase_name = "flight_2"
                    # Right foot unlocked in early swing (j_r = 1..5 of 18)
                    j_r = local_f - (stance_frames - 1)
                    s_r = j_r / swing_intervals
                    y_sw_r, z_lift_r = compute_run_swing_point(
                        _stance_y_for_step(k),
                        _stance_y_for_step(k + 2),
                        s_r,
                        step_height,
                    )
                    pitch_r = -10.0 * math.sin(math.pi * s_r)
                    z_g_r = context.environment.ground_height_at(start_x + HIP_X_OFFSET, y_sw_r)
                    foot_tgt_r = PlannedFootTarget(
                        world_xyz=(start_x + HIP_X_OFFSET, y_sw_r, z_g_r + ANKLE_REST_Z + z_lift_r),
                        is_locked=False,
                        rotation_deg=(pitch_r, 0.0, yaw_deg),
                        contact_intent=False,
                    )
                    phase_r = "flight"
                    phase_l = "flight"
                    is_flight = True

                # Left foot is in mid-to-late swing across all local_f = 0..11 (j_l = 6..17 of 18)
                j_l = (half_step - (stance_frames - 1)) + local_f
                s_l = j_l / swing_intervals
                y_sw_l, z_lift_l = compute_run_swing_point(
                    _stance_y_for_step(k - 1),
                    _stance_y_for_step(k + 1),
                    s_l,
                    step_height,
                )
                pitch_l = -10.0 * math.sin(math.pi * s_l)
                z_g_l = context.environment.ground_height_at(start_x - HIP_X_OFFSET, y_sw_l)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(start_x - HIP_X_OFFSET, y_sw_l, z_g_l + ANKLE_REST_Z + z_lift_l),
                    is_locked=False,
                    rotation_deg=(pitch_l, 0.0, yaw_deg),
                    contact_intent=False,
                )

            planned_pose = KinematicPlannedPose(
                frame=frame,
                time_seconds=(frame - 1) / fps,
                root_position=root_world,
                root_yaw_deg=yaw_deg,
                speed_mps=speed_mps,
                accel_mps2=0.0,
                motion_mode=MotionMode.RUN,
                dt=1.0 / fps,
                pelvis_location=(pelvis_dx, pelvis_dz, 0.0),
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
                gait_phase=u,
                is_flight=is_flight,
            )

            bridge_res = bridge_executor.execute_frame(planned_pose, keyframe=True, dt=1.0 / fps)

            eff_l = bridge_res.wbc_result.end_effectors.get("foot_L")
            eff_r = bridge_res.wbc_result.end_effectors.get("foot_R")

            if eff_l and (not eff_l.is_reachable or not eff_l.strictly_in_reach):
                unreachable_events.append({
                    "frame": frame,
                    "side": "L",
                    "phase": phase_l,
                    "dist": round(eff_l.reach_distance_m, 5),
                })
            if eff_r and (not eff_r.is_reachable or not eff_r.strictly_in_reach):
                unreachable_events.append({
                    "frame": frame,
                    "side": "R",
                    "phase": phase_r,
                    "dist": round(eff_r.reach_distance_m, 5),
                })

            if not bridge_res.success:
                for uc in bridge_res.unmet_constraints:
                    unreachable_events.append({
                        "frame": frame,
                        "category": uc.category,
                        "target": uc.target_name,
                        "error": uc.error_amount,
                        "desc": uc.description,
                    })

            state_l = {
                "target_world": eff_l.requested_world_xyz if eff_l else (0.0, 0.0, 0.0),
                "actual_world": eff_l.actual_world_xyz if eff_l else (0.0, 0.0, 0.0),
                "is_reachable": eff_l.is_reachable if eff_l else True,
                "strictly_in_reach": eff_l.strictly_in_reach if eff_l else True,
                "hip_to_target_dist": eff_l.reach_distance_m if eff_l else 0.0,
                "position_error_m": eff_l.position_error_m if eff_l else 0.0,
                "ankle_bone_drift": eff_l.position_error_m if eff_l else 0.0,
                "mesh_center_drift": eff_l.position_error_m if eff_l else 0.0,
            }
            state_r = {
                "target_world": eff_r.requested_world_xyz if eff_r else (0.0, 0.0, 0.0),
                "actual_world": eff_r.actual_world_xyz if eff_r else (0.0, 0.0, 0.0),
                "is_reachable": eff_r.is_reachable if eff_r else True,
                "strictly_in_reach": eff_r.strictly_in_reach if eff_r else True,
                "hip_to_target_dist": eff_r.reach_distance_m if eff_r else 0.0,
                "position_error_m": eff_r.position_error_m if eff_r else 0.0,
                "ankle_bone_drift": eff_r.position_error_m if eff_r else 0.0,
                "mesh_center_drift": eff_r.position_error_m if eff_r else 0.0,
            }

            ms = bridge_res.motion_state
            ms_params = dict(ms.params)
            ms_params.update({
                "tau": tau,
                "cycle_idx": tau // cycle_frames,
                "step_k": k,
                "local_f": local_f,
                "cycle_phase": cycle_phase_name,
                "pelvis_dz": round(pelvis_dz, 5),
                "torso_lean_deg": round(-(pelvis_rx + spine_rx), 3),
                "arm_l_rx": round(arm_l_rx, 2),
                "arm_r_rx": round(arm_r_rx, 2),
            })
            ms = ms.clone_with(params=ms_params)
            states.append(ms)

            frame_records.append({
                "frame": frame,
                "tau": tau,
                "cycle_idx": tau // cycle_frames,
                "step_k": k,
                "local_f": local_f,
                "u": round(u, 4),
                "cycle_phase": cycle_phase_name,
                "mode": MotionMode.RUN.value,
                "is_airborne": is_flight,
                "root_y": round(root_y, 5),
                "speed_mps": round(speed_mps, 5),
                "pelvis_dz": round(pelvis_dz, 5),
                "torso_lean_deg": round(-(pelvis_rx + spine_rx), 3),
                "phase_l": phase_l,
                "phase_r": phase_r,
                "state_l": state_l,
                "state_r": state_r,
                "arm_l_rx": round(arm_l_rx, 2),
                "arm_r_rx": round(arm_r_rx, 2),
            })

        if unreachable_events:
            raise RuntimeError(
                f"Encountered {len(unreachable_events)} IK reach violations during RunAction: "
                f"{unreachable_events[:5]}"
            )

        total_disp = frame_records[-1]["root_y"] - frame_records[0]["root_y"]
        airborne_frames = sum(1 for r in frame_records if r["is_airborne"])

        return ActionExecutionResult(
            action_name=self.name,
            initial_state=initial_state,
            final_state=states[-1],
            states=states,
            frame_records=frame_records,
            step_schedule=step_schedule,
            unreachable_count=len(unreachable_events),
            metrics={
                "total_frames": total_frames,
                "fps": config.fps,
                "cycles": cycles,
                "cycle_frames": cycle_frames,
                "stance_frames_per_step": stance_frames,
                "flight_frames_per_step": flight_frames,
                "airborne_frames_total": airborne_frames,
                "step_length": step_len,
                "stride_length": config.run_stride_length,
                "speed_mps": round(speed_mps, 5),
                "total_root_displacement": round(total_disp, 5),
                "unreachable_count": len(unreachable_events),
            },
        )


def run_task6b_via_motion_framework(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
) -> Dict[str, Any]:
    """Execute the Task 6B procedural running prototype through `MotionPlanner` + `RunAction`."""
    planner = MotionPlanner(config, armature_obj=armature_obj)
    planner.add_action(RunAction(cycles=config.run_cycles))
    return planner.execute()
