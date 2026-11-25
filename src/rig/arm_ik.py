"""Procedural two-bone arm IK and independent hand orientation control (Task 6F-A / Task 10-A).

Builds on the existing 19-bone CharacterArmature from Task 4B and complements leg IK (Task 4C):
- Creates dedicated Empty control objects for left/right hand IK targets (`HandIK.L`, `HandIK.R`)
  and elbow pole targets (`ElbowPole.L`, `ElbowPole.R`).
- Configures Blender native `IK` constraints (`chain_count = 2`) on `forearm.L` and `forearm.R`
  so `upper_arm` + `forearm` form a deterministic two-bone IK chain per arm.
- Configures elbow flexion constraints and pre-bend solver hints with matched `pole_angle = -90.0 deg`
  to guarantee natural forward/inward elbow flexion and outward/backward olecranon projection.
- Configures native `COPY_ROTATION` constraints on `hand.L` and `hand.R` targeting `HandIK.L` / `HandIK.R`
  in world space, enabling independent 3D hand orientation control decoupled from IK arm solving.
- Zero-impact backward compatibility:
  - Bone hierarchy and naming are 100% preserved.
  - IK constraints and rotation constraints default to `influence = 0.0`.
  - When influence is 0.0, the armature evaluates 100% identical to the original FK arm swing.
- Programmatic API:
  - `setup_arm_ik(...)`: idempotent configuration of arm IK constraints and empties.
  - `set_hand_ik_target(...)`: sets independent world-space position, 3D hand rotation, and elbow pole.
  - `set_arm_ik_influence(...)`: smoothly blends between FK (0.0) and IK (1.0).
  - `reset_arm_ik(...)`: resets arm IK targets and sets influence back to 0.0.
  - `get_arm_ik_state(...)`: inspects actual bone lengths, target error, orientation error, and reachability.

Task 10-A Contracts:
- Setup Idempotency: setup_arm_ik() ensures controls and constraints exist with correct configuration,
  without resetting active positions, orientations, or influences.
- Explicit Reset: reset_arm_ik() actively restores neutral rest positions and influence=0.0 while
  respecting existing effective parent transforms and rotation modes.
- Effective Parent Matrix: M_eff = M_parent @ matrix_parent_inverse handles world translation and
  rotation inversion across arbitrary valid conformal parent hierarchies.
- Rotation Mode Fidelity: preserves controller active rotation_mode across 6 Euler modes, QUATERNION,
  and AXIS_ANGLE without forced conversion to XYZ.
- Dependency Graph Freshness: synchronizes view layer before computing effective parent matrices.
"""

from typing import Dict, Optional, Tuple

import bpy

ARM_IK_TARGET_NAMES: Dict[str, str] = {"L": "HandIK.L", "R": "HandIK.R"}
ARM_POLE_TARGET_NAMES: Dict[str, str] = {"L": "ElbowPole.L", "R": "ElbowPole.R"}
ARM_IK_CONSTRAINT_NAMES: Dict[str, str] = {"L": "ArmIK.L", "R": "ArmIK.R"}
HAND_ROT_CONSTRAINT_NAMES: Dict[str, str] = {"L": "HandRotation.L", "R": "HandRotation.R"}

# Segment geometry matching Task 4B specifications (meters)
SHOULDER_X_OFFSET: float = 0.24
SHOULDER_REST_Z: float = 1.54
ELBOW_REST_Z: float = 1.24
WRIST_REST_Z: float = 0.98
HAND_TIP_REST_Z: float = 0.88

UPPER_ARM_LENGTH: float = 0.30
FOREARM_LENGTH: float = 0.26
HAND_LENGTH: float = 0.10

MAX_ARM_REACH: float = UPPER_ARM_LENGTH + FOREARM_LENGTH  # 0.56 m
MIN_ARM_REACH: float = 0.08  # Minimum distance avoiding degenerate zero-length vectors

DEFAULT_POLE_BACKWARD_OFFSET: float = 0.40  # Meters backward (-Y) from arm plane
DEFAULT_POLE_OUTWARD_OFFSET: float = 0.08   # Meters outward (X) from arm plane

_REQUIRED_ARM_IK_BONE_NAMES: Tuple[str, ...] = (
    "upper_arm.L",
    "upper_arm.R",
    "forearm.L",
    "forearm.R",
    "hand.L",
    "hand.R",
)


def setup_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    initial_influence: float = 0.0,
) -> Dict[str, bpy.types.Object]:
    """Configure native Blender two-bone arm IK chains, elbow pole targets, and hand orientation controls.

    This function is strictly idempotent:
    - Preserves existing controller objects, parents, matrices, positions, orientations, and rotation modes.
    - Preserves existing constraint instances, configurations, and active influences.
    - Only initializes neutral rest positions when creating brand new controllers.
    - Only sets initial_influence when creating brand new constraints.
    - Only applies pre-bend hints when initializing a previously unconstrained arm.

    Args:
        armature_obj: Optional CharacterArmature object.
        initial_influence: Initial constraint influence in [0.0, 1.0]. Defaults to 0.0 (FK mode).

    Returns:
        Dict mapping controller names ('HandIK.L', 'HandIK.R', 'ElbowPole.L', 'ElbowPole.R')
        to their Empty objects.
    """
    from src.scene_transaction_integrity import wiring as _sti_wiring

    return _sti_wiring.setup_arm_ik(
        armature_obj,
        initial_influence,
    )


def set_arm_ik_influence(
    armature_obj: Optional[bpy.types.Object] = None,
    side: str = "BOTH",
    influence: float = 1.0,
) -> None:
    """Set the IK and rotation constraint influence for one or both arms.

    Args:
        armature_obj: Optional CharacterArmature object.
        side: 'L', 'R', or 'BOTH'.
        influence: Influence value in [0.0, 1.0].
    """
    from src.scene_transaction_integrity import wiring as _sti_wiring

    return _sti_wiring.set_arm_ik_influence(
        armature_obj,
        side,
        influence,
    )


def reset_arm_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset both arms, empties, and constraint influences back to neutral rest (FK mode).

    Follows the Gate A-3 Transaction Atomicity Contract:
    - Phase 1: Resolves Armature and CharacterRoot, updates view layer.
    - Phase 2: Preflights effective parent transforms for all existing controllers on both sides (L and R)
      using compute_effective_parent_matrix() and validate_effective_parent_transform().
      If any preflight check fails, aborts immediately with ZERO scene writes on either side.
    - Phase 3: Enters unified _arm_rig_transaction(arm) context.
    - Phase 4: Executes bilateral reset with observable fault injection boundaries.
    - Phase 5: Synchronizes dependency graph and commits. Any write exception triggers atomic rollback.
    """
    from src.scene_transaction_integrity import wiring as _sti_wiring

    return _sti_wiring.reset_arm_ik(armature_obj)


def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    from src.scene_transaction_integrity import wiring as _sti_wiring

    return _sti_wiring.get_arm_ik_state(armature_obj, side)


def set_hand_ik_target(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    world_xyz: Tuple[float, float, float],
    hand_rotation_deg: Optional[Tuple[float, float, float]] = None,
    pole_world_xyz: Optional[Tuple[float, float, float]] = None,
    clamp_reach: bool = True,
    influence: float = 1.0,
) -> dict:
    """Set the left ('L') or right ('R') hand IK target in world coordinates.

    Follows the 10-A, 10-B-1, and 10-B-2 Pre-validation and Zero-Side-Effect Contracts:
    - Phase A: Validates all user inputs strictly before any scene access or mutation.
    - Phase B: Preflights dependency graph (view_layer.update()) and validates effective
      parent transforms of existing and anticipated controllers before auto-initialization.
    - Phase C: Invokes setup_arm_ik() only after Phase B validation succeeds with zero mutation.
    - Phase D: Computes targets, checks finite derived coordinates, and commits transforms/influences.
    - HandIK and ElbowPole transforms are resolved independently using their respective M_eff.
    - Preserves controller active rotation_mode (Euler modes, QUATERNION, AXIS_ANGLE).
    - Rejects non-conformal transforms (shears, non-uniform scaling, reflections, singularities).
    - Preserves default neutral orientation matching CharacterRoot when hand_rotation_deg is None.

    Args:
        armature_obj: Optional CharacterArmature object.
        side: Arm side, 'L' or 'R'.
        world_xyz: Desired wrist position in world coordinates (meters).
        hand_rotation_deg: Desired hand 3D Euler orientation in world coordinates (degrees, 'XYZ').
        pole_world_xyz: Optional explicit elbow pole target in world coordinates.
        clamp_reach: If True, out-of-reach targets are safely projected onto the sphere of radius
            `MAX_ARM_REACH` (or `MIN_ARM_REACH`) centered at the shoulder. If False, target is
            unclamped (bone lengths are still strictly preserved via use_stretch=False).
        influence: Constraint influence to set on ArmIK and HandRotation in [0.0, 1.0]. Defaults to 1.0.

    Returns:
        dict containing state information including requested/applied positions, target error,
        rotation error, reachability flag, and clamping status.
    """
    from src.scene_transaction_integrity import wiring as _sti_wiring

    return _sti_wiring.set_hand_ik_target(
        armature_obj,
        side,
        world_xyz,
        hand_rotation_deg,
        pole_world_xyz,
        clamp_reach,
        influence,
    )
