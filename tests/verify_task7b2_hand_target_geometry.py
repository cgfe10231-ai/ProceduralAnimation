"""TASK 7B-2 — Environmental Surface to Wrist Position & 3D Orientation Verification Suite (T01–T14).

Verifies ``src.motion.contact_model.compute_hand_target_from_surface()`` against
live `output/dynamics_playground.blend` mesh queries (T01–T03) and explicit
SO(3) / palm-anchor / covariance / negative boundary contracts (T04–T14)
without creating duplicate controllers, modifying scene assets, executing IK/ROM
solvers, or establishing contacts.

Intended execution (only after independent Diff review authorization):
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b --factory-startup --python-exit-code 1 --python tests/verify_task7b2_hand_target_geometry.py -- --failfast
"""

from __future__ import annotations

import copy
import hashlib
import math
import os
import sys
import unittest
from typing import Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bpy
from mathutils import Euler, Matrix, Vector

from src.motion.contact_model import (
    DEFAULT_LIMB_LOCAL_ANCHORS,
    ContactLifecycle,
    ContactRecord,
    ContactType,
    compute_hand_target_from_surface,
)
from src.scene.blender_mesh_query_adapter import create_mesh_backed_dynamics_query
from src.scene.environment_query import DynamicsEnvironmentQuery, SurfaceQueryResult

PLAYGROUND_BLEND = os.path.join(REPO_ROOT, "output", "dynamics_playground.blend")
METRIC_TOL = 1e-5


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: _sha256_file
# PURPOSE: Compute SHA-256 hex digest of a binary file without altering it.
# REASON: TASK 7B-2 (T14) — Verify `output/dynamics_playground.blend` byte-level immutability across the suite.
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: _open_playground_query
# PURPOSE: Open `output/dynamics_playground.blend` read-only and build a mesh-backed `DynamicsEnvironmentQuery` scoped to `Playground_Surfaces`.
# REASON: TASK 7B-2 (T01–T03) — Reuse Task 7B-1 accepted live mesh query acquisition on the single training ground asset.
def _open_playground_query() -> DynamicsEnvironmentQuery:
    if not os.path.isfile(PLAYGROUND_BLEND):
        raise FileNotFoundError(f"Authoritative playground blend missing: {PLAYGROUND_BLEND}")
    bpy.ops.wm.open_mainfile(filepath=PLAYGROUND_BLEND)
    bpy.context.view_layer.update()
    return create_mesh_backed_dynamics_query(
        scene=bpy.context.scene,
        collection_names=("Playground_Surfaces",),
        prefer_mesh=True,
        ground_z=0.0,
    )


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: _make_constructed_mesh_surface
# PURPOSE: Build an explicitly labeled test-constructed `SurfaceQueryResult` for mathematical boundary tests (never representing live scene sampling).
# REASON: TASK 7B-2 (T04–T14) — Isolate geometric math, covariance, and negative validation checks with deterministic inputs.
def _make_constructed_mesh_surface(
    surface_id: str,
    contact_point_world: Tuple[float, float, float],
    surface_normal_world: Tuple[float, float, float],
    *,
    success: bool = True,
    source_type: str = "mesh",
    surface_type: str = "vertical_wall",
    error_reason: Optional[str] = None,
) -> SurfaceQueryResult:
    return SurfaceQueryResult(
        surface_id=surface_id,
        surface_type=surface_type,
        contact_point_world=contact_point_world,
        surface_normal_world=surface_normal_world,
        signed_distance=0.0,
        friction_coeff=0.65,
        allows_regular_support=False,
        success=success,
        ray_hit_distance=0.0 if success else None,
        error_reason=error_reason,
        source_type=source_type,
    )


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: _matrix_from_euler_deg
# PURPOSE: Convert `(rx_deg, ry_deg, rz_deg)` 'XYZ' Euler angles in degrees to a 3x3 `mathutils.Matrix`.
# REASON: TASK 7B-2 — Evaluate orientation invariants directly in SO(3) without comparing raw Euler components.
def _matrix_from_euler_deg(rot_deg: Tuple[float, float, float]) -> Matrix:
    return Euler(
        (
            math.radians(rot_deg[0]),
            math.radians(rot_deg[1]),
            math.radians(rot_deg[2]),
        ),
        "XYZ",
    ).to_matrix()


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: _max_matrix_diff
# PURPOSE: Compute maximum entrywise absolute difference between two 3x3 matrices.
# REASON: TASK 7B-2 (T07, T08, T10, T11) — Quantify SO(3) orthogonality and rotation matrix covariance tolerances (`<= 1e-5`).
def _max_matrix_diff(a: Matrix, b: Matrix) -> float:
    return max(abs(a[r][c] - b[r][c]) for r in range(3) for c in range(3))


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: _assert_hand_target_contract
# PURPOSE: Verify SO(3) basis orthogonality, determinant == 1, outward normal and tangent alignment, and ContactRecord forward anchor reconstruction within `1e-5`.
# REASON: TASK 7B-2 (T01–T09) — Enforce uniform numerical geometry tolerances and emit observable physical metrics.
def _assert_hand_target_contract(
    tc: unittest.TestCase,
    test_id: str,
    side: str,
    surface: SurfaceQueryResult,
    tangent_hint_world: Tuple[float, float, float],
    wrist_world_xyz: Tuple[float, float, float],
    hand_rotation_deg: Tuple[float, float, float],
) -> Tuple[Matrix, float]:
    tc.assertEqual(len(wrist_world_xyz), 3)
    tc.assertEqual(len(hand_rotation_deg), 3)
    tc.assertTrue(all(math.isfinite(c) for c in wrist_world_xyz))
    tc.assertTrue(all(math.isfinite(a) for a in hand_rotation_deg))

    rot_mat = _matrix_from_euler_deg(hand_rotation_deg)
    col_x = Vector((rot_mat[0][0], rot_mat[1][0], rot_mat[2][0]))
    col_y = Vector((rot_mat[0][1], rot_mat[1][1], rot_mat[2][1]))
    col_z = Vector((rot_mat[0][2], rot_mat[1][2], rot_mat[2][2]))

    ortho_err = _max_matrix_diff(rot_mat.transposed() @ rot_mat, Matrix.Identity(3))
    det_err = abs(rot_mat.determinant() - 1.0)
    rh_err = (col_x.cross(col_y) - col_z).length

    n_expected = Vector(surface.surface_normal_world).normalized()
    t_hint_unit = Vector(tangent_hint_world).normalized()
    t_expected = (t_hint_unit - t_hint_unit.dot(n_expected) * n_expected).normalized()

    normal_err = (col_z - n_expected).length
    tangent_err = (col_y - t_expected).length

    anchor_local = DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"]
    rec = ContactRecord(
        contact_id=f"verify_7b2_{test_id}_{side}",
        limb=f"hand_{side}",
        surface_id=surface.surface_id,
        contact_type=ContactType.UNILATERAL,
        lifecycle=ContactLifecycle.CANDIDATE,
        world_position=surface.contact_point_world,
        world_normal=surface.surface_normal_world,
        body_local_anchor=anchor_local,
    )
    bone_mat_world = Matrix.Translation(Vector(wrist_world_xyz)) @ rot_mat.to_4x4()
    reconstructed_anchor = rec.compute_body_anchor_world_position(bone_mat_world)
    anchor_err_m = (Vector(reconstructed_anchor) - Vector(surface.contact_point_world)).length

    tc.assertLessEqual(ortho_err, METRIC_TOL, f"{test_id} ortho_err={ortho_err:.3e} > {METRIC_TOL}")
    tc.assertLessEqual(det_err, METRIC_TOL, f"{test_id} det_err={det_err:.3e} > {METRIC_TOL}")
    tc.assertLessEqual(rh_err, METRIC_TOL, f"{test_id} right_handed_err={rh_err:.3e} > {METRIC_TOL}")
    tc.assertLessEqual(normal_err, METRIC_TOL, f"{test_id} normal_err={normal_err:.3e} > {METRIC_TOL}")
    tc.assertLessEqual(tangent_err, METRIC_TOL, f"{test_id} tangent_err={tangent_err:.3e} > {METRIC_TOL}")
    tc.assertLessEqual(anchor_err_m, METRIC_TOL, f"{test_id} anchor_err_m={anchor_err_m:.3e} > {METRIC_TOL}")

    print(
        f"[7B-2][{test_id}] side={side} surface_id={surface.surface_id!r} "
        f"wrist_world_xyz={wrist_world_xyz} hand_rotation_deg={hand_rotation_deg} "
        f"reconstructed_anchor={reconstructed_anchor} anchor_err_m={anchor_err_m:.3e} "
        f"normal_err={normal_err:.3e} tangent_err={tangent_err:.3e} "
        f"ortho_err={ortho_err:.3e} det_err={det_err:.3e}",
        flush=True,
    )
    return rot_mat, anchor_err_m


# [INTRODUCED 2026-11-28T13:58:00+08:00]
# FUNCTION: TestTask7B2HandTargetGeometry
# PURPOSE: Execute verification matrix T01–T14 for `compute_hand_target_from_surface()`.
# REASON: TASK 7B-2 — Validate surface-to-hand target position and 3D orientation geometry contract prior to Phase 7B-3 integration.
class TestTask7B2HandTargetGeometry(unittest.TestCase):
    """Standalone TASK 7B-2 verification matrix (T01–T14)."""

    _initial_blend_sha256: str = ""

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.setUpClass
    # PURPOSE: Record and print initial SHA-256 checksum of `output/dynamics_playground.blend`.
    # REASON: TASK 7B-2 — Guard source `.blend` immutability across all T01–T14 cases.
    @classmethod
    def setUpClass(cls) -> None:
        if not os.path.isfile(PLAYGROUND_BLEND):
            raise FileNotFoundError(f"Playground blend missing: {PLAYGROUND_BLEND}")
        cls._initial_blend_sha256 = _sha256_file(PLAYGROUND_BLEND)
        print(f"[7B-2][setUpClass] blend={PLAYGROUND_BLEND} initial_sha256={cls._initial_blend_sha256}", flush=True)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.tearDownClass
    # PURPOSE: Verify and print post-suite SHA-256 checksum of `output/dynamics_playground.blend`.
    # REASON: TASK 7B-2 — Guarantee source `.blend` remained byte-identical after execution.
    @classmethod
    def tearDownClass(cls) -> None:
        final_sha = _sha256_file(PLAYGROUND_BLEND)
        print(
            f"[7B-2][tearDownClass] blend={PLAYGROUND_BLEND} "
            f"initial_sha256={cls._initial_blend_sha256} final_sha256={final_sha} "
            f"unchanged={final_sha == cls._initial_blend_sha256}",
            flush=True,
        )
        if final_sha != cls._initial_blend_sha256:
            raise AssertionError(
                f"Playground blend modified! before={cls._initial_blend_sha256} after={final_sha}"
            )

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t01_real_wall_target_conversion
    # PURPOSE: T01 — Convert real `Surface_VerticalWall` query result into wrist position and hand orientation for L/R sides.
    # REASON: TASK 7B-2 T01 — Validate geometric transform on live vertical wall obstacle target from Task 7B-1.
    def test_t01_real_wall_target_conversion(self) -> None:
        query = _open_playground_query()
        surf = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        self.assertTrue(surf.success)
        self.assertEqual(surf.source_type, "mesh")
        self.assertTrue(surf.surface_id.startswith("mesh:Surface_VerticalWall:"))

        tangent_hint = (0.0, 0.0, 1.0)
        for side in ("L", "R"):
            wrist_xyz, rot_deg = compute_hand_target_from_surface(side, surf, tangent_hint)
            _assert_hand_target_contract(self, "T01", side, surf, tangent_hint, wrist_xyz, rot_deg)
            anchor = DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"]
            # Outward wall normal is (0,-1,0), tangent +Z: wrist sits -anchor[2] outside wall along -Y and -anchor[1] along -Z
            expected_wrist = (
                surf.contact_point_world[0] - anchor[0],
                surf.contact_point_world[1] + anchor[2],
                surf.contact_point_world[2] - anchor[1],
            )
            self.assertLessEqual((Vector(wrist_xyz) - Vector(expected_wrist)).length, METRIC_TOL)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t02_real_vault_box_top_target_conversion
    # PURPOSE: T02 — Convert real `Surface_VaultBox` top-surface query result into wrist position and hand orientation for L/R sides.
    # REASON: TASK 7B-2 T02 — Validate geometric transform on live vault box top target from Task 7B-1.
    def test_t02_real_vault_box_top_target_conversion(self) -> None:
        query = _open_playground_query()
        surf = query.query_spatial_surface((0.0, 28.0, 1.2), (0.0, 0.0, -1.0), max_distance=2.0)
        self.assertTrue(surf.success)
        self.assertEqual(surf.source_type, "mesh")
        self.assertTrue(surf.surface_id.startswith("mesh:Surface_VaultBox:"))

        tangent_hint = (0.0, 1.0, 0.0)
        for side in ("L", "R"):
            wrist_xyz, rot_deg = compute_hand_target_from_surface(side, surf, tangent_hint)
            _assert_hand_target_contract(self, "T02", side, surf, tangent_hint, wrist_xyz, rot_deg)
            anchor = DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"]
            expected_wrist = (
                surf.contact_point_world[0] - anchor[0],
                surf.contact_point_world[1] - anchor[1],
                surf.contact_point_world[2] - anchor[2],
            )
            self.assertLessEqual((Vector(wrist_xyz) - Vector(expected_wrist)).length, METRIC_TOL)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t03_real_ledge_bar_bottom_target_conversion
    # PURPOSE: T03 — Convert real `Surface_LedgeBar_Crossbar` underside query result into wrist position and hand orientation for L/R sides.
    # REASON: TASK 7B-2 T03 — Validate geometric transform on live overhead bar underside target using `surface_id` provenance without surface-name branching.
    def test_t03_real_ledge_bar_bottom_target_conversion(self) -> None:
        query = _open_playground_query()
        surf = query.query_spatial_surface((0.0, 32.0, 1.95), (0.0, 0.0, 1.0), max_distance=2.0)
        self.assertTrue(surf.success)
        self.assertEqual(surf.source_type, "mesh")
        self.assertTrue(surf.surface_id.startswith("mesh:Surface_LedgeBar_Crossbar:"))

        tangent_hint = (0.0, 1.0, 0.0)
        for side in ("L", "R"):
            wrist_xyz, rot_deg = compute_hand_target_from_surface(side, surf, tangent_hint)
            _assert_hand_target_contract(self, "T03", side, surf, tangent_hint, wrist_xyz, rot_deg)
            anchor = DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"]
            # Outward normal is (0,0,-1), tangent +Y => x_axis = (-1,0,0)
            expected_wrist = (
                surf.contact_point_world[0] + anchor[0],
                surf.contact_point_world[1] - anchor[1],
                surf.contact_point_world[2] + anchor[2],
            )
            self.assertLessEqual((Vector(wrist_xyz) - Vector(expected_wrist)).length, METRIC_TOL)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t04_bilateral_hand_local_anchor_contract
    # PURPOSE: T04 — Verify left/right outputs consume `DEFAULT_LIMB_LOCAL_ANCHORS['hand_L']` and `['hand_R']` directly.
    # REASON: TASK 7B-2 T04 — Ensure hand wrist offset derives strictly from canonical limb anchor definitions without hardcoding constants.
    def test_t04_bilateral_hand_local_anchor_contract(self) -> None:
        surf = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_anchor_contract:0",
            contact_point_world=(1.2, -3.4, 2.5),
            surface_normal_world=(0.0, -1.0, 0.0),
        )
        tangent_hint = (0.0, 0.0, 1.0)
        for side in ("L", "R"):
            expected_anchor = DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"]
            self.assertEqual(len(expected_anchor), 3)
            self.assertTrue(all(math.isfinite(v) for v in expected_anchor))
            wrist_xyz, rot_deg = compute_hand_target_from_surface(side, surf, tangent_hint)
            rot_mat, anchor_err = _assert_hand_target_contract(
                self, "T04", side, surf, tangent_hint, wrist_xyz, rot_deg
            )
            delta_local = rot_mat.transposed() @ (Vector(surf.contact_point_world) - Vector(wrist_xyz))
            anchor_local_err = (delta_local - Vector(expected_anchor)).length
            self.assertLessEqual(anchor_local_err, METRIC_TOL)
            self.assertLessEqual(anchor_err, METRIC_TOL)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t05_non_axis_aligned_tilted_surface
    # PURPOSE: T05 — Verify non-axis-aligned tilted test surface and oblique non-orthogonal tangent hint project accurately into tangent plane.
    # REASON: TASK 7B-2 T05 — Confirm full 3D oblique basis projection without axis-aligned special cases.
    def test_t05_non_axis_aligned_tilted_surface(self) -> None:
        n_vec = Vector((0.30, -0.70, 0.65)).normalized()
        surf = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_tilted_plane:0",
            contact_point_world=(-0.4, 15.2, 1.45),
            surface_normal_world=(n_vec.x, n_vec.y, n_vec.z),
            surface_type="sloped_ramp",
        )
        tangent_hint = (0.80, 0.50, -0.20)
        for side in ("L", "R"):
            wrist_xyz, rot_deg = compute_hand_target_from_surface(side, surf, tangent_hint)
            rot_mat, _ = _assert_hand_target_contract(
                self, "T05", side, surf, tangent_hint, wrist_xyz, rot_deg
            )
            col_y = Vector((rot_mat[0][1], rot_mat[1][1], rot_mat[2][1]))
            col_z = Vector((rot_mat[0][2], rot_mat[1][2], rot_mat[2][2]))
            self.assertLessEqual(abs(col_y.dot(col_z)), METRIC_TOL)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t06_same_surface_different_tangents
    # PURPOSE: T06 — Verify distinct tangent hints on the same surface yield different in-plane hand rotations while preserving identical surface normal alignment and palm contact point.
    # REASON: TASK 7B-2 T06 — Confirm tangent hint controls in-plane yaw around fixed surface outward normal.
    def test_t06_same_surface_different_tangents(self) -> None:
        n_vec = Vector((0.25, -0.80, 0.55)).normalized()
        surf = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_same_surface:0",
            contact_point_world=(0.35, 22.0, 1.40),
            surface_normal_world=(n_vec.x, n_vec.y, n_vec.z),
        )
        t1 = (0.0, 0.0, 1.0)
        t2 = (1.0, 0.2, 0.0)
        w1, r1_deg = compute_hand_target_from_surface("L", surf, t1)
        w2, r2_deg = compute_hand_target_from_surface("L", surf, t2)
        m1, _ = _assert_hand_target_contract(self, "T06-A", "L", surf, t1, w1, r1_deg)
        m2, _ = _assert_hand_target_contract(self, "T06-B", "L", surf, t2, w2, r2_deg)

        z1 = Vector((m1[0][2], m1[1][2], m1[2][2]))
        z2 = Vector((m2[0][2], m2[1][2], m2[2][2]))
        self.assertLessEqual((z1 - z2).length, METRIC_TOL)
        mat_diff = _max_matrix_diff(m1, m2)
        self.assertGreater(mat_diff, 0.25)
        wrist_diff = (Vector(w1) - Vector(w2)).length
        self.assertGreater(wrist_diff, 0.02)
        print(f"[7B-2][T06] mat_diff={mat_diff:.6f} wrist_diff_m={wrist_diff:.6f}", flush=True)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t07_so3_orthogonality_and_right_handedness
    # PURPOSE: T07 — Sweep arbitrary normal/tangent configurations and verify R^T R == I, det(R) == +1, and cyclic right-handed cross products within `1e-5`.
    # REASON: TASK 7B-2 T07 — Guarantee valid SO(3) orientation frames across arbitrary 3D directions without left-handed reflection.
    def test_t07_so3_orthogonality_and_right_handedness(self) -> None:
        configs = [
            ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
            ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
            ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            (tuple(Vector((1.0, 2.0, 3.0)).normalized()), (-1.0, 0.5, 0.2)),
            (tuple(Vector((-2.0, -1.0, 0.5)).normalized()), (0.3, -1.2, 0.8)),
        ]
        worst_ortho = 0.0
        worst_det = 0.0
        for idx, (norm, hint) in enumerate(configs):
            surf = _make_constructed_mesh_surface(
                f"mesh:TEST_CONSTRUCTED_so3_{idx}:0",
                contact_point_world=(0.1 * idx, 10.0 + idx, 1.0),
                surface_normal_world=norm,
            )
            wrist_xyz, rot_deg = compute_hand_target_from_surface("R", surf, hint)
            rot_mat, _ = _assert_hand_target_contract(
                self, f"T07-{idx}", "R", surf, hint, wrist_xyz, rot_deg
            )
            ortho_err = _max_matrix_diff(rot_mat.transposed() @ rot_mat, Matrix.Identity(3))
            det_err = abs(rot_mat.determinant() - 1.0)
            col_x = Vector((rot_mat[0][0], rot_mat[1][0], rot_mat[2][0]))
            col_y = Vector((rot_mat[0][1], rot_mat[1][1], rot_mat[2][1]))
            col_z = Vector((rot_mat[0][2], rot_mat[1][2], rot_mat[2][2]))
            self.assertLessEqual((col_x.cross(col_y) - col_z).length, METRIC_TOL)
            self.assertLessEqual((col_y.cross(col_z) - col_x).length, METRIC_TOL)
            self.assertLessEqual((col_z.cross(col_x) - col_y).length, METRIC_TOL)
            worst_ortho = max(worst_ortho, ortho_err)
            worst_det = max(worst_det, det_err)
        print(f"[7B-2][T07] cases={len(configs)} worst_ortho_err={worst_ortho:.3e} worst_det_err={worst_det:.3e}", flush=True)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t08_xyz_euler_roundtrip_via_rotation_matrix
    # PURPOSE: T08 — Verify 'XYZ' Euler output reconstructs the exact target SO(3) matrix within `1e-5` (including +/-Y normal near-gimbal cases) without comparing raw Euler components.
    # REASON: TASK 7B-2 T08 — Avoid Euler aliasing false failures while guaranteeing rotation fidelity in SO(3).
    def test_t08_xyz_euler_roundtrip_via_rotation_matrix(self) -> None:
        cases = [
            ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),      # +90 deg X/Y/Z gimbal boundary check
            ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),      # +90 deg Y gimbal boundary check
            ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            (tuple(Vector((0.4, -0.6, 0.69282032)).normalized()), (0.5, 0.4, 0.7)),
        ]
        worst_mat_err = 0.0
        for idx, (norm, hint) in enumerate(cases):
            n = Vector(norm).normalized()
            t_unit = Vector(hint).normalized()
            y = (t_unit - t_unit.dot(n) * n).normalized()
            x = y.cross(n).normalized()
            y = n.cross(x).normalized()
            r_expected = Matrix(((x.x, y.x, n.x), (x.y, y.y, n.y), (x.z, y.z, n.z)))

            surf = _make_constructed_mesh_surface(
                f"mesh:TEST_CONSTRUCTED_euler_rt_{idx}:0",
                contact_point_world=(0.0, 20.0, 1.2),
                surface_normal_world=(n.x, n.y, n.z),
            )
            _, rot_deg = compute_hand_target_from_surface("L", surf, hint)
            r_roundtrip = _matrix_from_euler_deg(rot_deg)
            mat_err = _max_matrix_diff(r_roundtrip, r_expected)
            worst_mat_err = max(worst_mat_err, mat_err)
            self.assertLessEqual(mat_err, METRIC_TOL, f"Roundtrip SO(3) error {mat_err:.3e} > {METRIC_TOL}")
        print(f"[7B-2][T08] cases={len(cases)} worst_roundtrip_mat_err={worst_mat_err:.3e}", flush=True)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t09_forward_contact_anchor_reconstruction
    # PURPOSE: T09 — Reconstruct world palm contact anchor via existing `ContactRecord.compute_body_anchor_world_position()` and verify geometric compliance error `<= 1e-5`.
    # REASON: TASK 7B-2 T09 — Close the forward/inverse geometric loop between `compute_hand_target_from_surface()` and `ContactRecord`.
    def test_t09_forward_contact_anchor_reconstruction(self) -> None:
        query = _open_playground_query()
        live_probes = [
            ((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            ((0.0, 28.0, 1.2), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
            ((0.0, 32.0, 1.95), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        ]
        surfaces = [query.query_spatial_surface(pt, d, max_distance=2.0) for pt, d, _ in live_probes]
        hints = [h for _, _, h in live_probes]
        surfaces.append(
            _make_constructed_mesh_surface(
                "mesh:TEST_CONSTRUCTED_forward_tilted:0",
                contact_point_world=(0.6, 18.4, 1.55),
                surface_normal_world=tuple(Vector((0.2, -0.8, 0.56)).normalized()),
            )
        )
        hints.append((0.7, 0.2, 0.6))

        max_pos_err = 0.0
        for idx, (surf, hint) in enumerate(zip(surfaces, hints)):
            for side in ("L", "R"):
                wrist_xyz, rot_deg = compute_hand_target_from_surface(side, surf, hint)
                rot_mat = _matrix_from_euler_deg(rot_deg)
                rec = ContactRecord(
                    contact_id=f"verify_7b2_t09_{idx}_{side}",
                    limb=f"hand_{side}",
                    surface_id=surf.surface_id,
                    contact_type=ContactType.UNILATERAL,
                    lifecycle=ContactLifecycle.ESTABLISHED,
                    world_position=surf.contact_point_world,
                    world_normal=surf.surface_normal_world,
                    body_local_anchor=DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"],
                )
                bone_mat_world = Matrix.Translation(Vector(wrist_xyz)) @ rot_mat.to_4x4()
                anchor_world = rec.compute_body_anchor_world_position(bone_mat_world)
                geom = rec.check_geometric_compliance(anchor_world)
                max_pos_err = max(max_pos_err, geom.total_position_error_m)
                self.assertTrue(geom.is_valid)
                self.assertLessEqual(geom.total_position_error_m, METRIC_TOL)
        print(f"[7B-2][T09] checks={len(surfaces) * 2} max_anchor_compliance_err_m={max_pos_err:.3e}", flush=True)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t10_environment_translation_covariance
    # PURPOSE: T10 — Verify translating surface point by `d` preserves rotation `R_h' == R_h` and translates wrist by exact `p_w' = p_w + d` within `1e-5`.
    # REASON: TASK 7B-2 T10 — Prove SE(3) translation covariance of target geometry conversion.
    def test_t10_environment_translation_covariance(self) -> None:
        d = Vector((1.25, -0.75, 0.80))
        surf_orig = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_trans_base:0",
            contact_point_world=(-0.4, 23.8, 1.3),
            surface_normal_world=tuple(Vector((0.2, -0.9, 0.38729833)).normalized()),
        )
        p_s_shifted = Vector(surf_orig.contact_point_world) + d
        surf_shifted = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_trans_shifted:0",
            contact_point_world=(p_s_shifted.x, p_s_shifted.y, p_s_shifted.z),
            surface_normal_world=surf_orig.surface_normal_world,
        )
        hint = (0.3, 0.1, 0.9)
        for side in ("L", "R"):
            p_w, rot_deg = compute_hand_target_from_surface(side, surf_orig, hint)
            p_w_p, rot_deg_p = compute_hand_target_from_surface(side, surf_shifted, hint)
            r_h = _matrix_from_euler_deg(rot_deg)
            r_h_p = _matrix_from_euler_deg(rot_deg_p)

            pos_cov_err = (Vector(p_w_p) - (Vector(p_w) + d)).length
            rot_cov_err = _max_matrix_diff(r_h_p, r_h)
            self.assertLessEqual(pos_cov_err, METRIC_TOL)
            self.assertLessEqual(rot_cov_err, METRIC_TOL)
            print(
                f"[7B-2][T10] side={side} pos_cov_err_m={pos_cov_err:.3e} rot_cov_mat_err={rot_cov_err:.3e}",
                flush=True,
            )

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t11_environment_rotation_covariance
    # PURPOSE: T11 — Verify rotating surface point, normal, and tangent hint jointly by `Q in SO(3)` yields `p_w' = Q @ p_w` and `R_h' = Q @ R_h` within `1e-5`.
    # REASON: TASK 7B-2 T11 — Prove SO(3) rotation equivariance/covariance of hand frame and wrist placement.
    def test_t11_environment_rotation_covariance(self) -> None:
        q_mat = Euler((math.radians(22.0), math.radians(-31.0), math.radians(48.0)), "XYZ").to_matrix()
        n_orig = Vector((0.15, -0.85, 0.50497525)).normalized()
        p_orig = Vector((0.35, 23.8, 1.30))
        t_orig = Vector((0.40, 0.25, 0.88))

        p_rot = q_mat @ p_orig
        n_rot = (q_mat @ n_orig).normalized()
        t_rot = q_mat @ t_orig

        surf_orig = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_rot_base:0",
            contact_point_world=(p_orig.x, p_orig.y, p_orig.z),
            surface_normal_world=(n_orig.x, n_orig.y, n_orig.z),
        )
        surf_rot = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_rot_cov:0",
            contact_point_world=(p_rot.x, p_rot.y, p_rot.z),
            surface_normal_world=(n_rot.x, n_rot.y, n_rot.z),
        )
        for side in ("L", "R"):
            p_w, rot_deg = compute_hand_target_from_surface(
                side, surf_orig, (t_orig.x, t_orig.y, t_orig.z)
            )
            p_w_p, rot_deg_p = compute_hand_target_from_surface(
                side, surf_rot, (t_rot.x, t_rot.y, t_rot.z)
            )
            r_h = _matrix_from_euler_deg(rot_deg)
            r_h_p = _matrix_from_euler_deg(rot_deg_p)

            pos_cov_err = (Vector(p_w_p) - (q_mat @ Vector(p_w))).length
            rot_cov_err = _max_matrix_diff(r_h_p, q_mat @ r_h)
            self.assertLessEqual(pos_cov_err, METRIC_TOL)
            self.assertLessEqual(rot_cov_err, METRIC_TOL)
            print(
                f"[7B-2][T11] side={side} pos_cov_err_m={pos_cov_err:.3e} rot_cov_mat_err={rot_cov_err:.3e}",
                flush=True,
            )

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t12_invalid_inputs_and_failed_query_rejection
    # PURPOSE: T12 — Reject failed queries, non-mesh sources, invalid sides, invalid identities, wrong dimensions, NaN/Inf, and non-unit normals cleanly with diagnostic exceptions.
    # REASON: TASK 7B-2 T12 — Enforce zero-fallback contract boundaries before computing derived poses.
    def test_t12_invalid_inputs_and_failed_query_rejection(self) -> None:
        valid_surf = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_valid:0",
            contact_point_world=(0.0, 23.8, 1.3),
            surface_normal_world=(0.0, -1.0, 0.0),
        )
        valid_hint = (0.0, 0.0, 1.0)

        cases = [
            ("failed_query", "L", _make_constructed_mesh_surface("none", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), success=False, source_type="none", error_reason="NO_HIT: empty"), valid_hint),
            ("source_analytical", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), source_type="analytical"), valid_hint),
            ("source_default", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), source_type="default"), valid_hint),
            ("source_none", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), source_type="none"), valid_hint),
            ("side_both", "BOTH", valid_surf, valid_hint),
            ("side_lower", "l", valid_surf, valid_hint),
            ("side_empty", "", valid_surf, valid_hint),
            ("side_int", 1, valid_surf, valid_hint),
            ("surface_not_dataclass", "L", {"surface_id": "mesh:TEST:0"}, valid_hint),
            ("id_empty", "L", _make_constructed_mesh_surface("", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_spaces", "L", _make_constructed_mesh_surface("   ", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_none", "L", _make_constructed_mesh_surface("none", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_default_ground", "L", _make_constructed_mesh_surface("default_ground", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_prefix_only", "L", _make_constructed_mesh_surface("mesh:", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_missing_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_empty_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall:", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_spaces_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall:   ", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_non_numeric_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall:abc", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_decimal_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall:1.5", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_non_ascii_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall:\u00b2", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_plus_poly", "L", _make_constructed_mesh_surface("mesh:Surface_VerticalWall:+1", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_empty_obj", "L", _make_constructed_mesh_surface("mesh::0", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_spaces_obj", "L", _make_constructed_mesh_surface("mesh:   :0", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("id_neg_poly", "L", _make_constructed_mesh_surface("mesh:Wall:-1", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("dim_point_2d", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),  # type: ignore[arg-type]
            ("dim_hint_4d", "L", valid_surf, (0.0, 0.0, 1.0, 0.0)),  # type: ignore[arg-type]
            ("type_hint_bool", "L", valid_surf, (True, 0.0, 1.0)),  # type: ignore[arg-type]
            ("nan_point", "L", _make_constructed_mesh_surface("mesh:TEST:0", (float("nan"), 0.0, 0.0), (0.0, 0.0, 1.0)), valid_hint),
            ("inf_normal", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, 0.0, float("inf"))), (1.0, 0.0, 0.0)),
            ("neg_inf_hint", "L", valid_surf, (0.0, 0.0, float("-inf"))),
            ("norm_zero", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)), valid_hint),
            ("norm_double", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, -2.0, 0.0)), valid_hint),
            ("norm_short_tol", "L", _make_constructed_mesh_surface("mesh:TEST:0", (0.0, 0.0, 0.0), (0.0, -0.9999, 0.0)), valid_hint),
        ]
        for label, side_arg, surf_arg, hint_arg in cases:
            with self.subTest(case=label):
                with self.assertRaises((ValueError, TypeError)) as ctx:
                    compute_hand_target_from_surface(side_arg, surf_arg, hint_arg)
                msg = str(ctx.exception)
                self.assertTrue(len(msg.strip()) > 0)
                print(f"[7B-2][T12] rejected case={label} exc={type(ctx.exception).__name__} reason={msg!r}", flush=True)

        # [INTRODUCED 2026-11-28T14:07:00+08:00]
        # FUNCTION: TestTask7B2HandTargetGeometry.test_t12 (BUG-01 positive colon-containing object name)
        # PURPOSE: Verify valid Blender object names containing colons with trailing non-negative ASCII polygon index are accepted.
        # REASON: TASK 7B-2 BUG-01 — Confirm `rpartition(":")` handles object names containing colons without false rejection.
        for colon_sid in ("mesh:NS:SubRig:Surface_VerticalWall:12", "mesh:Character:Wall:Front:0"):
            surf_colon = _make_constructed_mesh_surface(
                colon_sid,
                contact_point_world=(0.0, 23.8, 1.3),
                surface_normal_world=(0.0, -1.0, 0.0),
            )
            wrist_c, rot_c = compute_hand_target_from_surface("L", surf_colon, valid_hint)
            _assert_hand_target_contract(self, "T12-COLON", "L", surf_colon, valid_hint, wrist_c, rot_c)

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t13_zero_parallel_and_near_degenerate_tangent_rejection
    # PURPOSE: T13 — Reject zero, parallel, and near-degenerate (`<= 1e-6` projection) tangent hints, while proving scale invariance (`1e-8`, `1`, `1e8`) and float64 near-degenerate (`> 1e-6`) accuracy.
    # REASON: TASK 7B-2 T13 / BUG-02 — Verify Step 6–8 projection threshold (`<= 1e-6`) rejection and IEEE-754 float64 scale/precision fidelity.
    def test_t13_zero_parallel_and_near_degenerate_tangent_rejection(self) -> None:
        surf_wall = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_degen_wall:0",
            contact_point_world=(0.0, 23.8, 1.3),
            surface_normal_world=(0.0, -1.0, 0.0),
        )
        n_tilt = Vector((0.3, -0.7, 0.65)).normalized()
        surf_tilt = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_degen_tilt:0",
            contact_point_world=(0.0, 20.0, 1.2),
            surface_normal_world=(n_tilt.x, n_tilt.y, n_tilt.z),
        )
        cases = [
            ("zero_vec", surf_wall, (0.0, 0.0, 0.0)),
            ("sub_tol_vec", surf_wall, (0.0, 1e-8, 0.0)),
            ("exact_parallel", surf_wall, (0.0, -1.0, 0.0)),
            ("exact_antiparallel", surf_wall, (0.0, 1.0, 0.0)),
            ("near_parallel_wall", surf_wall, (1e-7, -1.0, 0.0)),
            ("near_parallel_tilt", surf_tilt, (n_tilt.x + 1e-7, n_tilt.y, n_tilt.z)),
        ]
        for label, surf_arg, hint_arg in cases:
            with self.subTest(case=label):
                with self.assertRaises(ValueError) as ctx:
                    compute_hand_target_from_surface("L", surf_arg, hint_arg)
                msg = str(ctx.exception)
                self.assertTrue(len(msg.strip()) > 0)
                print(f"[7B-2][T13] rejected case={label} reason={msg!r}", flush=True)

        # [INTRODUCED 2026-11-28T14:07:00+08:00]
        # FUNCTION: TestTask7B2HandTargetGeometry.test_t13 (BUG-02 scale invariance and near-degenerate positive cases)
        # PURPOSE: Verify scaling a legal tangent hint by `1e-8`, `1`, and `1e8` yields consistent wrist position and SO(3) rotation, and verify a non-axis-aligned near-degenerate hint (`proj > 1e-6`) matches an independent known orthogonal basis within `1e-5`.
        # REASON: TASK 7B-2 BUG-02 — Confirm elimination of `1e-6` pre-normalization length threshold and float64 projection accuracy.
        base_hint = (0.8, 0.5, -0.2)
        for side in ("L", "R"):
            w_ref, r_ref_deg = compute_hand_target_from_surface(side, surf_tilt, base_hint)
            m_ref = _matrix_from_euler_deg(r_ref_deg)
            for scale in (1e-8, 1.0, 1e8):
                scaled_hint = (base_hint[0] * scale, base_hint[1] * scale, base_hint[2] * scale)
                w_s, r_s_deg = compute_hand_target_from_surface(side, surf_tilt, scaled_hint)
                m_s = _matrix_from_euler_deg(r_s_deg)
                pos_diff = (Vector(w_s) - Vector(w_ref)).length
                mat_diff = _max_matrix_diff(m_s, m_ref)
                self.assertLessEqual(pos_diff, METRIC_TOL)
                self.assertLessEqual(mat_diff, METRIC_TOL)
                print(
                    f"[7B-2][T13-SCALE] side={side} scale={scale:.0e} "
                    f"pos_diff_m={pos_diff:.3e} rot_mat_diff={mat_diff:.3e}",
                    flush=True,
                )

        # Independent exact Pythagorean orthogonal pair in float64:
        # |(2, -3, 6)| = 7, |(3, 6, 2)| = 7, and (2,-3,6).(3,6,2) = 6 - 18 + 12 = 0 identically.
        n_exact = (2.0 / 7.0, -3.0 / 7.0, 6.0 / 7.0)
        t_exact = (3.0 / 7.0, 6.0 / 7.0, 2.0 / 7.0)
        x_exact = (
            t_exact[1] * n_exact[2] - t_exact[2] * n_exact[1],
            t_exact[2] * n_exact[0] - t_exact[0] * n_exact[2],
            t_exact[0] * n_exact[1] - t_exact[1] * n_exact[0],
        )
        r_expected_indep = Matrix((
            (x_exact[0], t_exact[0], n_exact[0]),
            (x_exact[1], t_exact[1], n_exact[1]),
            (x_exact[2], t_exact[2], n_exact[2]),
        ))
        surf_pyth = _make_constructed_mesh_surface(
            "mesh:TEST_CONSTRUCTED_near_degen_positive:0",
            contact_point_world=(0.5, 19.0, 1.35),
            surface_normal_world=n_exact,
        )
        for eps_sin in (2e-6, 5e-6):
            cos_theta = math.sqrt(1.0 - eps_sin * eps_sin)
            hint_near_pos = (
                cos_theta * n_exact[0] + eps_sin * t_exact[0],
                cos_theta * n_exact[1] + eps_sin * t_exact[1],
                cos_theta * n_exact[2] + eps_sin * t_exact[2],
            )
            for side in ("L", "R"):
                w_near, r_near_deg = compute_hand_target_from_surface(side, surf_pyth, hint_near_pos)
                m_near = _matrix_from_euler_deg(r_near_deg)
                indep_rot_err = _max_matrix_diff(m_near, r_expected_indep)
                self.assertLessEqual(indep_rot_err, METRIC_TOL)
                expected_wrist_indep = Vector(surf_pyth.contact_point_world) - (
                    r_expected_indep @ Vector(DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"])
                )
                indep_wrist_err = (Vector(w_near) - expected_wrist_indep).length
                self.assertLessEqual(indep_wrist_err, METRIC_TOL)
                print(
                    f"[7B-2][T13-NEAR-POS] side={side} proj_len={eps_sin:.1e} "
                    f"indep_rot_mat_err={indep_rot_err:.3e} indep_wrist_err_m={indep_wrist_err:.3e}",
                    flush=True,
                )

    # [INTRODUCED 2026-11-28T13:58:00+08:00]
    # FUNCTION: TestTask7B2HandTargetGeometry.test_t14_repeat_consistency_and_zero_state_side_effects
    # PURPOSE: T14 — Verify repeated calls produce deterministic independent tuples without mutating input `SurfaceQueryResult`, anchors, scene objects, or source `.blend`.
    # REASON: TASK 7B-2 T14 — Confirm strict statelessness and zero hidden side effects.
    def test_t14_repeat_consistency_and_zero_state_side_effects(self) -> None:
        self.assertEqual(_sha256_file(PLAYGROUND_BLEND), self._initial_blend_sha256)
        query = _open_playground_query()
        obj_names_before = sorted(obj.name for obj in bpy.data.objects)
        anchors_snapshot = copy.deepcopy(DEFAULT_LIMB_LOCAL_ANCHORS)

        surf = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        surf_snapshot = copy.deepcopy(surf)
        hint = (0.2, 0.0, 1.0)

        w0, r0 = compute_hand_target_from_surface("L", surf, hint)
        self.assertIsInstance(w0, tuple)
        self.assertIsInstance(r0, tuple)
        for _ in range(20):
            w_rep, r_rep = compute_hand_target_from_surface("L", surf, hint)
            self.assertEqual(w_rep, w0)
            self.assertEqual(r_rep, r0)
            self.assertIsNot(w_rep, w0)
            self.assertIsNot(r_rep, r0)

        self.assertEqual(surf, surf_snapshot)
        self.assertEqual(DEFAULT_LIMB_LOCAL_ANCHORS, anchors_snapshot)
        self.assertEqual(sorted(obj.name for obj in bpy.data.objects), obj_names_before)
        self.assertEqual(_sha256_file(PLAYGROUND_BLEND), self._initial_blend_sha256)
        print(
            f"[7B-2][T14] repeat_calls=20 object_count={len(obj_names_before)} "
            f"wrist_xyz={w0} rot_deg={r0} blend_unchanged=True",
            flush=True,
        )


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1 :])
    unittest.main(argv=argv, verbosity=2)
