"""Procedural motion generation package (Task 5A, Task 5B, Task 5C, Task 6A, 6B, Task 6C & Task 6D)."""

from src.config import PipelineConfig
from src.motion.forward_walk import compute_forward_swing_point, generate_forward_walk
from src.motion.framework import (
    ActionExecutionResult,
    BlenderPoseApplicator,
    ContactConstraintAdapter,
    ContactPointState,
    EnvironmentQuery,
    MotionAction,
    MotionMode,
    MotionPlanner,
    MotionRuntimeContext,
    MotionState,
    StartStopWalkAction,
    create_initial_motion_state,
    forward_unit_vector_from_yaw,
    right_unit_vector_from_yaw,
    root_local_to_world_vector,
    run_task5c_via_motion_framework,
    world_to_root_local_vector,
)
from src.motion.run_cycle import (
    RunAction,
    apply_run_upper_body_pose,
    compute_run_swing_point,
    run_task6b_via_motion_framework,
)
from src.motion.sprint_brake import (
    SprintBrakeAction,
    apply_brake_pose,
    evaluate_brake_root_kinematics,
    run_task6d_via_motion_framework,
)
from src.motion.sprint_start import (
    SprintStartAction,
    build_sprint_schedule,
    evaluate_sprint_root_kinematics,
    run_task6c_via_motion_framework,
)
from src.motion.start_stop_walk import (
    build_step_schedule,
    evaluate_root_kinematics,
    generate_start_stop_walk,
)
from src.motion.walk_cycle import compute_swing_trajectory, generate_walk_cycle
from src.motion.rigid_link import (
    BodyMassDistribution,
    DEFAULT_HUMAN_TOTAL_MASS_KG,
    DEMPSTER_13_SEGMENT_MODEL,
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    RigidSegmentSpec,
    SegmentCoMResult,
    WholeBodyCoMResult,
    compute_whole_body_com,
    create_custom_mass_distribution,
)
from src.motion.joint_limits import (
    ConstraintMode,
    AxisViolation,
    JointViolation,
    JointValidationResult,
    AxisModification,
    JointModification,
    JointClampResult,
    JointLimitSpec,
    JointModel,
    DEFAULT_HUMANOID_ROM_MODEL,
    create_custom_joint_model,
    extract_evaluated_bone_rotation_rad,
    normalize_angle_deg,
    normalize_angle_rad,
)
from src.motion.whole_body_controller import (
    EndEffectorFeedback,
    EndEffectorTarget,
    UnmetConstraint,
    WholeBodyControlResult,
    WholeBodyControlTargets,
    WholeBodyController,
)


def apply_motion(config: PipelineConfig, rig_obj=None):
    """Apply procedural walk cycle keyframes to the character rig."""
    return generate_walk_cycle(config, armature_obj=rig_obj)


__all__ = [
    "apply_motion",
    "compute_swing_trajectory",
    "generate_walk_cycle",
    "compute_forward_swing_point",
    "generate_forward_walk",
    "build_step_schedule",
    "evaluate_root_kinematics",
    "generate_start_stop_walk",
    "MotionMode",
    "ContactPointState",
    "MotionState",
    "EnvironmentQuery",
    "ContactConstraintAdapter",
    "BlenderPoseApplicator",
    "MotionRuntimeContext",
    "ActionExecutionResult",
    "MotionAction",
    "StartStopWalkAction",
    "RunAction",
    "SprintStartAction",
    "SprintBrakeAction",
    "build_sprint_schedule",
    "evaluate_sprint_root_kinematics",
    "evaluate_brake_root_kinematics",
    "apply_brake_pose",
    "run_task6c_via_motion_framework",
    "run_task6d_via_motion_framework",
    "MotionPlanner",
    "create_initial_motion_state",
    "run_task5c_via_motion_framework",
    "run_task6b_via_motion_framework",
    "compute_run_swing_point",
    "apply_run_upper_body_pose",
    "forward_unit_vector_from_yaw",
    "right_unit_vector_from_yaw",
    "world_to_root_local_vector",
    "root_local_to_world_vector",
    "RigidSegmentSpec",
    "BodyMassDistribution",
    "SegmentCoMResult",
    "WholeBodyCoMResult",
    "DEFAULT_HUMAN_TOTAL_MASS_KG",
    "DEMPSTER_WINTER_15_SEGMENT_MODEL",
    "DEMPSTER_13_SEGMENT_MODEL",
    "compute_whole_body_com",
    "create_custom_mass_distribution",
    "ConstraintMode",
    "AxisViolation",
    "JointViolation",
    "JointValidationResult",
    "AxisModification",
    "JointModification",
    "JointClampResult",
    "JointLimitSpec",
    "JointModel",
    "DEFAULT_HUMANOID_ROM_MODEL",
    "create_custom_joint_model",
    "extract_evaluated_bone_rotation_rad",
    "normalize_angle_deg",
    "normalize_angle_rad",
    "EndEffectorTarget",
    "EndEffectorFeedback",
    "UnmetConstraint",
    "WholeBodyControlTargets",
    "WholeBodyControlResult",
    "WholeBodyController",
]

