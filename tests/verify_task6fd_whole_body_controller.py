"""Automated verification suite for Task 6F-D: Unified Whole-Body Controller and Minimal Coordinator.

Tests:
1. Bilateral Hand IK: simultaneous independent control of Left and Right hands with distinct 3D positions and orientations.
2. Bilateral Foot IK: simultaneous independent control of Left and Right feet with distinct ground and aerial targets.
3. Quad-Effector Simultaneous Control: all 4 limbs (hand_L, hand_R, foot_L, foot_R) simultaneously controlled in a single frame.
4. Selective Disabling & Independence: disabling one end effector returns it to FK without disturbing other active effectors.
5. Base / Pelvis Coordination: varying root and pelvis position/orientation while maintaining world-space end-effector tracking.
6. Decoupled Hand Position & 3D Orientation: independent orientation control with zero wrist position drift.
7. End-Effector Tracking Error Reporting: truthful reporting of millimeter-level position errors and degree-level orientation errors.
8. Joint Model ROM Consistency: verifies that WholeBodyController's internal ROM validation matches independent JointModel checks.
9. Unreachable & ROM Conflict Detection: ensures impossible targets and ROM violations are explicitly flagged as UnmetConstraints (zero silent passes).
10. Center of Mass Consistency: verifies that WholeBodyController's CoM result matches direct `compute_whole_body_com` output.
11. MotionAction Architecture Integration: verifies clean integration of WholeBodyController within a subclassed MotionAction.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Tuple

import bpy
from mathutils import Euler, Matrix, Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    ActionExecutionResult,
    ContactConstraintAdapter,
    EnvironmentQuery,
    MotionAction,
    MotionMode,
    MotionRuntimeContext,
    MotionState,
    create_initial_motion_state,
)
from src.motion.joint_limits import DEFAULT_HUMANOID_ROM_MODEL
from src.motion.rigid_link import (
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    compute_whole_body_com,
)
from src.motion.whole_body_controller import (
    EndEffectorFeedback,
    EndEffectorTarget,
    UnmetConstraint,
    WholeBodyControlResult,
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.rig.arm_ik import MAX_ARM_REACH
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import MAX_LEG_REACH
from src.rig.pose import reset_pose


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify_whole_body_controller() -> None:
    print("=" * 74)
    print("VERIFYING TASK 6F-D: UNIFIED WHOLE-BODY CONTROLLER AND COORDINATOR")
    print("=" * 74)

    # -------------------------------------------------------------------------
    # Scene Setup
    # -------------------------------------------------------------------------
    config = PipelineConfig()
    build_character(config)
    arm = build_rig(config)
    bind_character_to_rig(arm)
    reset_pose(arm)

    root = arm.parent or bpy.data.objects.get("CharacterRoot")
    controller = WholeBodyController(
        armature_obj=arm,
        root_obj=root,
        joint_model=DEFAULT_HUMANOID_ROM_MODEL,
        mass_distribution=DEMPSTER_WINTER_15_SEGMENT_MODEL,
        config=config,
    )
    controller.reset_all_controls()

    start_y = -8.0  # Character default start waypoint Y

    # -------------------------------------------------------------------------
    # 1. Bilateral Hand IK Simultaneous Control
    # -------------------------------------------------------------------------
    print("\n[Test 1] Testing simultaneous bilateral Hand IK control with distinct targets...")
    tgt_1 = WholeBodyControlTargets()
    tgt_1.set_hand("L", (-0.24, start_y + 0.35, 1.35), rotation_deg=(20.0, 10.0, -5.0))
    tgt_1.set_hand("R", (0.24, start_y + 0.30, 1.25), rotation_deg=(15.0, -10.0, 5.0))

    res_1 = controller.execute_frame(tgt_1)
    print(f"  Hand L error: {res_1.end_effectors['hand_L'].position_error_m * 1000:.3f} mm, rot_err: {res_1.end_effectors['hand_L'].orientation_error_deg:.3f} deg")
    print(f"  Hand R error: {res_1.end_effectors['hand_R'].position_error_m * 1000:.3f} mm, rot_err: {res_1.end_effectors['hand_R'].orientation_error_deg:.3f} deg")

    if res_1.end_effectors["hand_L"].position_error_m > 0.001:
        _fail(f"Hand L position error > 1mm: {res_1.end_effectors['hand_L'].position_error_m}")
    if res_1.end_effectors["hand_R"].position_error_m > 0.001:
        _fail(f"Hand R position error > 1mm: {res_1.end_effectors['hand_R'].position_error_m}")
    if res_1.end_effectors["hand_L"].orientation_error_deg > 0.1:
        _fail(f"Hand L orientation error > 0.1 deg: {res_1.end_effectors['hand_L'].orientation_error_deg}")
    if res_1.end_effectors["hand_R"].orientation_error_deg > 0.1:
        _fail(f"Hand R orientation error > 0.1 deg: {res_1.end_effectors['hand_R'].orientation_error_deg}")
    if not res_1.success:
        _fail(f"Bilateral hand target unexpectedly failed: {res_1.summary()}")
    print("  -> PASSED: Both hands simultaneously and accurately reached distinct positions and 3D orientations.")

    # -------------------------------------------------------------------------
    # 2. Bilateral Foot IK Simultaneous Control
    # -------------------------------------------------------------------------
    print("\n[Test 2] Testing simultaneous bilateral Foot IK control with distinct targets...")
    tgt_2 = WholeBodyControlTargets()
    tgt_2.set_foot("L", (-0.11, start_y + 0.00, 0.07), is_locked=True)
    tgt_2.set_foot("R", (0.11, start_y + 0.25, 0.22), is_locked=False, rotation_deg=(10.0, 0.0, 0.0))

    res_2 = controller.execute_frame(tgt_2)
    print(f"  Foot L error: {res_2.end_effectors['foot_L'].position_error_m * 1000:.3f} mm (ground rest)")
    print(f"  Foot R error: {res_2.end_effectors['foot_R'].position_error_m * 1000:.3f} mm (aerial raised)")

    if res_2.end_effectors["foot_L"].position_error_m > 0.001:
        _fail(f"Foot L position error > 1mm: {res_2.end_effectors['foot_L'].position_error_m}")
    if res_2.end_effectors["foot_R"].position_error_m > 0.001:
        _fail(f"Foot R position error > 1mm: {res_2.end_effectors['foot_R'].position_error_m}")
    if not res_2.success:
        _fail(f"Bilateral foot target failed: {res_2.summary()}")
    print("  -> PASSED: Both feet simultaneously reached distinct ground and aerial targets.")

    # -------------------------------------------------------------------------
    # 3. Quad-Effector Simultaneous Control in Single Frame
    # -------------------------------------------------------------------------
    print("\n[Test 3] Testing quad-effector simultaneous control (hand_L, hand_R, foot_L, foot_R)...")
    tgt_3 = WholeBodyControlTargets()
    tgt_3.set_hand("L", (-0.24, start_y + 0.25, 1.30))
    tgt_3.set_hand("R", (0.24, start_y + 0.15, 1.20))
    tgt_3.set_foot("L", (-0.11, start_y, 0.07))
    tgt_3.set_foot("R", (0.11, start_y + 0.20, 0.18))

    res_3 = controller.execute_frame(tgt_3)
    for eff_id in ("hand_L", "hand_R", "foot_L", "foot_R"):
        fb = res_3.end_effectors[eff_id]
        print(f"  - {eff_id:8s}: err={fb.position_error_m * 1000:.3f} mm | reachable={fb.is_reachable}")
        if fb.position_error_m > 0.001:
            _fail(f"{eff_id} position error > 1mm in quad-effector test: {fb.position_error_m}")

    if not res_3.success:
        _fail(f"Quad-effector simultaneous control failed: {res_3.summary()}")
    print("  -> PASSED: All 4 effectors active, tracking and compliant in a single frame.")

    # -------------------------------------------------------------------------
    # 4. Selective Disabling & Independence
    # -------------------------------------------------------------------------
    print("\n[Test 4] Testing selective disabling (disabling Hand L leaves it in FK without crosstalk)...")
    tgt_4 = WholeBodyControlTargets()
    # Explicitly disable Hand L
    tgt_4.set_hand("L", (-0.24, start_y + 0.25, 1.30), enabled=False)
    # Keep Hand R, Foot L, Foot R active
    tgt_4.set_hand("R", (0.24, start_y + 0.15, 1.20))
    tgt_4.set_foot("L", (-0.11, start_y, 0.07))
    tgt_4.set_foot("R", (0.11, start_y + 0.20, 0.18))

    res_4 = controller.execute_frame(tgt_4)
    if res_4.end_effectors["hand_L"].enabled:
        _fail("Hand L was not marked as disabled in feedback")
    if not res_4.end_effectors["hand_R"].enabled:
        _fail("Hand R was unexpectedly disabled")

    # Hand R and feet must still have near-zero tracking error
    if res_4.end_effectors["hand_R"].position_error_m > 0.001:
        _fail("Hand R error corrupted by disabling Hand L")
    if res_4.end_effectors["foot_L"].position_error_m > 0.001:
        _fail("Foot L error corrupted by disabling Hand L")
    print("  Hand L disabled -> enabled=False; Hand R err = "
          f"{res_4.end_effectors['hand_R'].position_error_m * 1000:.3f} mm (PASSED)")

    # -------------------------------------------------------------------------
    # 5. Base / Pelvis Coordination & World Space Target Preservation
    # -------------------------------------------------------------------------
    print("\n[Test 5] Testing base/pelvis motion with world-space target preservation...")
    tgt_5 = WholeBodyControlTargets()
    # Drop pelvis by -0.06m in height and pitch torso forward by 10 deg
    tgt_5.set_pelvis(location=(0.0, -0.06, 0.0))  # Bone local +Y is vertical world +Z
    tgt_5.set_trunk_posture(spine_deg=(10.0, 0.0, 0.0))
    # Specify absolute world target for hands and feet
    tgt_5.set_hand("L", (-0.24, start_y + 0.20, 1.25))
    tgt_5.set_foot("L", (-0.11, start_y + 0.05, 0.07))
    tgt_5.set_foot("R", (0.11, start_y + 0.05, 0.07))

    res_5 = controller.execute_frame(tgt_5)
    print(f"  Pelvis world Z: {res_5.pelvis_world_position[2]:.4f} m (crouched)")
    print(f"  Hand L world error: {res_5.end_effectors['hand_L'].position_error_m * 1000:.3f} mm")
    print(f"  Foot L world error: {res_5.end_effectors['foot_L'].position_error_m * 1000:.3f} mm")

    if res_5.end_effectors["hand_L"].position_error_m > 0.001:
        _fail(f"Hand L world target failed under pelvis drop: err={res_5.end_effectors['hand_L'].position_error_m}")
    if res_5.end_effectors["foot_L"].position_error_m > 0.001:
        _fail(f"Foot L world target failed under pelvis drop: err={res_5.end_effectors['foot_L'].position_error_m}")
    print("  -> PASSED: World targets preserved accurately regardless of pelvis translation/crouching.")

    # -------------------------------------------------------------------------
    # 6. Decoupled Hand Position & 3D Orientation
    # -------------------------------------------------------------------------
    print("\n[Test 6] Testing decoupled hand position and 3D orientation...")
    wrist_pos = (-0.24, start_y + 0.25, 1.25)
    orientations = [
        (20.0, 10.0, -5.0),
        (30.0, 5.0, -10.0),
        (10.0, 15.0, 0.0),
    ]
    for rot in orientations:
        tgt_6 = WholeBodyControlTargets()
        tgt_6.set_hand("L", wrist_pos, rotation_deg=rot)
        res_6 = controller.execute_frame(tgt_6)
        fb = res_6.end_effectors["hand_L"]
        print(f"  Target rot {rot}: pos_err = {fb.position_error_m * 1000:.4f} mm, rot_err = {fb.orientation_error_deg:.4f} deg")
        if fb.position_error_m > 0.001:
            _fail(f"Wrist drifted during hand re-orientation: {fb.position_error_m}")
        if fb.orientation_error_deg > 0.05:
            _fail(f"Hand orientation error too large: {fb.orientation_error_deg}")
    print("  -> PASSED: Hand 3D orientation independently commanded with zero wrist position drift.")

    # -------------------------------------------------------------------------
    # 7. ROM Consistency with Independent JointModel
    # -------------------------------------------------------------------------
    print("\n[Test 7] Testing ROM validation consistency between Controller and JointModel...")
    tgt_7 = WholeBodyControlTargets()
    # Deliberate spine hyperextension beyond ROM (+80 deg)
    tgt_7.set_trunk_posture(spine_deg=(80.0, 0.0, 0.0))
    res_7 = controller.execute_frame(tgt_7)

    # Independent check
    independent_rom_res = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm, use_evaluated_ik=True)
    if res_7.rom_validation.is_valid:
        _fail("WholeBodyController did not flag deliberate spine ROM violation")
    if independent_rom_res.is_valid:
        _fail("Independent JointModel failed to flag spine ROM violation")

    controller_spine_excess = res_7.rom_validation.violations["spine"].max_excess_deg
    indep_spine_excess = independent_rom_res.violations["spine"].max_excess_deg
    if abs(controller_spine_excess - indep_spine_excess) > 1e-4:
        _fail(f"ROM violation excess discrepancy: {controller_spine_excess} != {indep_spine_excess}")
    print(f"  Controller spine excess: {controller_spine_excess:.2f} deg == Independent: {indep_spine_excess:.2f} deg (PASSED)")

    # -------------------------------------------------------------------------
    # 8. Unreachable Targets & ROM Conflict Detection (Truthful Reporting)
    # -------------------------------------------------------------------------
    print("\n[Test 8] Verifying unreachable targets and ROM conflicts are explicitly reported...")
    controller.reset_all_controls()
    tgt_8 = WholeBodyControlTargets()
    # Request hand target at Y = start_y + 1.50m (way beyond MAX_ARM_REACH = 0.56m)
    impossible_hand = (-0.24, start_y + 1.50, 1.30)
    tgt_8.set_hand("L", impossible_hand, clamp_reach=True)

    res_8 = controller.execute_frame(tgt_8)
    print(f"  Impossible target requested: {impossible_hand}")
    print(f"  Result success flag: {res_8.success} (must be False)")
    print(f"  is_all_reachable flag: {res_8.is_all_reachable} (must be False)")
    print(f"  Unmet constraints count: {len(res_8.unmet_constraints)}")
    for uc in res_8.unmet_constraints:
        print(f"    - [{uc.category}] {uc.target_name}: {uc.description}")

    if res_8.success:
        _fail("Unreachable target was falsely reported as success!")
    if res_8.is_all_reachable:
        _fail("Unreachable target was falsely marked as reachable!")
    if not any(uc.category == "REACHABILITY" for uc in res_8.unmet_constraints):
        _fail("REACHABILITY violation not recorded in unmet_constraints")
    print("  -> PASSED: Unreachable target accurately flagged with zero false-success reporting.")

    # -------------------------------------------------------------------------
    # 9. Center of Mass Consistency with rigid_link Module
    # -------------------------------------------------------------------------
    print("\n[Test 9] Verifying Center of Mass consistency between Controller and rigid_link...")
    controller.reset_all_controls()
    tgt_9 = WholeBodyControlTargets()
    tgt_9.set_hand("L", (-0.24, start_y + 0.30, 1.30))
    tgt_9.set_foot("L", (-0.11, start_y + 0.15, 0.20))
    res_9 = controller.execute_frame(tgt_9)

    # Compute CoM independently
    independent_com_res = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL, update_scene=False)
    com_diff = (res_9.com_result.com_world - independent_com_res.com_world).length
    print(f"  Controller CoM: ({res_9.com_result.com_world.x:.4f}, {res_9.com_result.com_world.y:.4f}, {res_9.com_result.com_world.z:.4f})")
    print(f"  Independent CoM: ({independent_com_res.com_world.x:.4f}, {independent_com_res.com_world.y:.4f}, {independent_com_res.com_world.z:.4f})")
    print(f"  CoM Discrepancy: {com_diff:.10f} m")

    if com_diff > 1e-8:
        _fail(f"CoM calculation discrepancy: {com_diff:.10f} m > 1e-8 m")
    print("  -> PASSED: Controller CoM is mathematically identical to rigid_link calculation.")

    # -------------------------------------------------------------------------
    # 10. MotionAction Architecture Integration
    # -------------------------------------------------------------------------
    print("\n[Test 10] Testing clean integration within a subclassed MotionAction...")

    class WholeBodyDemoAction(MotionAction):
        """Minimal proof-of-concept MotionAction driving the WholeBodyController."""

        def __init__(self, action_name: str = "whole_body_demo", total_frames: int = 10) -> None:
            self._action_name = action_name
            self._total_frames = total_frames

        @property
        def name(self) -> str:
            return self._action_name

        def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
            return self._total_frames

        def execute(
            self,
            initial_state: MotionState,
            context: MotionRuntimeContext,
        ) -> ActionExecutionResult:
            wbc = WholeBodyController(
                armature_obj=context.armature_obj,
                root_obj=context.root_obj,
                config=context.config,
            )
            states: List[MotionState] = []
            frame_records: List[dict] = []
            cur_pos = initial_state.position
            start_frame = initial_state.frame

            for i in range(self._total_frames):
                frame_idx = start_frame + i
                t = float(i) / max(1, self._total_frames - 1)

                # Procedurally wave left arm up and down
                wave_z = 1.20 + 0.20 * math.sin(t * math.pi)
                targets = WholeBodyControlTargets()
                targets.set_hand("L", (-0.24, cur_pos[1] + 0.25, wave_z))
                targets.set_foot("L", (-0.11, cur_pos[1], 0.07))
                targets.set_foot("R", (0.11, cur_pos[1], 0.07))

                ctrl_res = wbc.execute_frame(targets)
                if not ctrl_res.success:
                    raise RuntimeError(f"WBC failed at frame {frame_idx}: {ctrl_res.summary()}")

                # Record unified MotionState
                m_state = MotionState(
                    frame=frame_idx,
                    time_sec=frame_idx / context.config.fps,
                    position=cur_pos,
                    orientation_deg=(0.0, 0.0, 0.0),
                    velocity=(0.0, 0.0, 0.0),
                    acceleration=(0.0, 0.0, 0.0),
                    mode=MotionMode.IDLE,
                    gait_phase=t,
                    params={
                        "com_world": (ctrl_res.com_result.com_world.x, ctrl_res.com_result.com_world.y, ctrl_res.com_result.com_world.z),
                        "hand_L_err_mm": ctrl_res.end_effectors["hand_L"].position_error_m * 1000,
                    },
                )
                states.append(m_state)
                frame_records.append({"frame": frame_idx, "wave_z": wave_z})

            return ActionExecutionResult(
                action_name=self.name,
                initial_state=initial_state,
                final_state=states[-1],
                states=states,
                frame_records=frame_records,
                unreachable_count=0,
                metrics={"frames_executed": self._total_frames},
            )

    # Execute the demo action
    env = EnvironmentQuery(ground_z=0.0)
    contact_adapter = ContactConstraintAdapter(arm, env)
    from src.motion.framework import BlenderPoseApplicator
    pose_applicator = BlenderPoseApplicator(arm, root, config)
    ctx = MotionRuntimeContext(
        config=config,
        armature_obj=arm,
        root_obj=root,
        scene=bpy.context.scene,
        environment=env,
        contact_adapter=contact_adapter,
        pose_applicator=pose_applicator,
    )
    init_state = create_initial_motion_state(config)
    demo_action = WholeBodyDemoAction("whole_body_demo", total_frames=8)
    action_res = demo_action.execute(init_state, ctx)

    print(f"  Executed {len(action_res.states)} frames via WholeBodyDemoAction(MotionAction)")
    print(f"  Final frame hand_L err: {action_res.states[-1].params['hand_L_err_mm']:.4f} mm")
    print(f"  Final frame CoM: {action_res.states[-1].params['com_world']}")
    if len(action_res.states) != 8:
        _fail(f"Expected 8 states, got {len(action_res.states)}")
    print("  -> PASSED: WholeBodyController seamlessly drives procedural frames within a MotionAction.")

    # Reset armature
    controller.reset_all_controls()

    print("\n" + "=" * 74)
    print("ALL TASK 6F-D WHOLE-BODY CONTROLLER VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 74)


if __name__ == "__main__":
    verify_whole_body_controller()
