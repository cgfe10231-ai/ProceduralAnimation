"""Procedural motion generation package (Task 5A, Task 5B & Task 5C)."""

from src.config import PipelineConfig
from src.motion.forward_walk import compute_forward_swing_point, generate_forward_walk
from src.motion.start_stop_walk import (
    build_step_schedule,
    evaluate_root_kinematics,
    generate_start_stop_walk,
)
from src.motion.walk_cycle import compute_swing_trajectory, generate_walk_cycle


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
]

