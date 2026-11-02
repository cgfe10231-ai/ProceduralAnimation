"""Shared transform utilities and effective parent matrix mathematics (Task 10-A / 09-B).

Consolidates the effective parent transform contract established in Task 09-B:
- M_eff = M_parent @ matrix_parent_inverse (or Identity if parent is None).
- Domain validation ensures only conformal transforms (pure rotation, positive uniform
  scale combined with rotation, and finite translation) are accepted.
- Rejects non-finite elements, non-affine matrices, reflections (det < 0), singular matrices
  (det == 0), degenerate scales (s^2 <= 1e-12), non-uniform scales, and shears.
- Provides unified world-to-local and local-to-world position and rotation mapping.
"""

import math
from typing import Optional

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector


def compute_effective_parent_matrix(obj: Optional[bpy.types.Object]) -> Matrix:
    """Compute effective parent matrix M_eff = M_parent @ matrix_parent_inverse.

    If obj is None or obj.parent is None, returns Matrix.Identity(4).
    """
    if obj is None or obj.parent is None:
        return Matrix.Identity(4)
    return obj.parent.matrix_world @ obj.matrix_parent_inverse


def validate_effective_parent_transform(eff_mat: Matrix, target_name: str) -> None:
    """Validate that the effective parent transform lies within the supported domain.

    The supported domain consists strictly of pure 3D rotations and positive uniform
    scales combined with rotations. Non-affine matrices, non-finite elements,
    singular matrices (det == 0), reflection matrices (det < 0), non-uniform scaling,
    and shearing are unsupported and rejected in Phase A before any scene mutation occurs.
    """
    for r in range(4):
        for c in range(4):
            if not math.isfinite(eff_mat[r][c]):
                raise ValueError(
                    f"Phase A effective parent transform validation failed for '{target_name}': "
                    f"non-finite matrix element at ({r}, {c}). "
                    f"The interface requires pure rotation or positive uniform scale with rotation."
                )

    if (
        abs(eff_mat[3][0]) > 1e-6
        or abs(eff_mat[3][1]) > 1e-6
        or abs(eff_mat[3][2]) > 1e-6
        or abs(eff_mat[3][3] - 1.0) > 1e-6
    ):
        raise ValueError(
            f"Phase A effective parent transform validation failed for '{target_name}': "
            f"non-affine matrix with bottom row {tuple(eff_mat[3])}. "
            f"The interface requires pure rotation or positive uniform scale with rotation."
        )

    a_mat = Matrix((
        (eff_mat[0][0], eff_mat[0][1], eff_mat[0][2]),
        (eff_mat[1][0], eff_mat[1][1], eff_mat[1][2]),
        (eff_mat[2][0], eff_mat[2][1], eff_mat[2][2]),
    ))
    det_a = a_mat.determinant()
    if det_a < 0.0:
        raise ValueError(
            f"Phase A effective parent transform validation failed for '{target_name}': "
            f"negative determinant det(A)={det_a:.6e} indicates reflection. "
            f"Singular transforms and reflections are unsupported; "
            f"the interface requires pure rotation or positive uniform scale with rotation."
        )
    if det_a == 0.0:
        raise ValueError(
            f"Phase A effective parent transform validation failed for '{target_name}': "
            f"singular matrix with zero determinant det(A)={det_a:.6e}. "
            f"Singular transforms and reflections are unsupported; "
            f"the interface requires pure rotation or positive uniform scale with rotation."
        )

    g_mat = a_mat.transposed() @ a_mat
    s_sq = (g_mat[0][0] + g_mat[1][1] + g_mat[2][2]) / 3.0
    if s_sq <= 1e-12:
        raise ValueError(
            f"Phase A effective parent transform validation failed for '{target_name}': "
            f"degenerate scale s^2={s_sq:.6e} <= 1e-12."
        )

    max_rel_dev = 0.0
    for r in range(3):
        for c in range(3):
            target_val = s_sq if r == c else 0.0
            dev = abs(g_mat[r][c] - target_val) / s_sq
            if dev > max_rel_dev:
                max_rel_dev = dev

    if max_rel_dev > 1e-6:
        raise ValueError(
            f"Phase A effective parent transform validation failed for '{target_name}': "
            f"non-conformal transform with relative deviation {max_rel_dev:.6e} > 1e-6. "
            f"Non-uniform scale and shear are unsupported; "
            f"the interface requires pure rotation or positive uniform scale with rotation."
        )


def world_to_local_position(world_pos: Vector, eff_parent_mat: Matrix) -> Vector:
    """Convert a world-space position vector to controller local space using effective parent matrix."""
    return eff_parent_mat.inverted() @ world_pos


def world_to_local_rotation(world_rot_euler: Euler, eff_parent_mat: Matrix) -> Euler:
    """Convert a world-space Euler rotation ('XYZ') to controller local Euler rotation ('XYZ').

    Extracts pure rotation from conformal effective parent matrix:
    R_eff = eff_parent_mat.to_quaternion().to_matrix()
    R_local = R_eff.inverted() @ R_world
    """
    world_rot_mat = world_rot_euler.to_matrix()
    parent_rot_mat = eff_parent_mat.to_quaternion().to_matrix()
    local_rot_mat = parent_rot_mat.inverted() @ world_rot_mat
    return local_rot_mat.to_euler("XYZ")
