"""TASK 7B-1 — Environmental End-Effector Target Acquisition Verification Suite (T01–T12).

Verifies that existing live Blender mesh query interfaces
(`create_mesh_backed_dynamics_query()`, `BlenderMeshEnvironmentAdapter`,
`DynamicsEnvironmentQuery.query_spatial_surface()`, `SurfaceQueryResult`)
acquire authentic 3D environmental targets directly from `output/dynamics_playground.blend`
(`Playground_Surfaces`, `prefer_mesh=True`) without adding any wrapper layer,
duplicating BVH/raycast logic, modifying production code, or altering the source `.blend`.

Intended execution (when separately authorized after Diff review):
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P tests/verify_task7b1_environment_targets.py
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
import unittest
from typing import Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bpy
from mathutils import Euler, Matrix, Vector

from src.scene.blender_mesh_query_adapter import create_mesh_backed_dynamics_query
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    SurfaceGeometryType,
    SurfaceQueryResult,
)

PLAYGROUND_BLEND = os.path.join(REPO_ROOT, "output", "dynamics_playground.blend")
POS_TOL_M = 1e-5
NORM_VEC_TOL = 1e-5
UNIT_NORM_TOL = 1e-6


# [INTRODUCED 2026-11-28T00:13:00+08:00]
# FUNCTION: _sha256_file
# PURPOSE: Compute SHA-256 digest of a binary file without mutating its contents.
# REASON: TASK 7B-1 (T12) — Verify `output/dynamics_playground.blend` byte-level integrity before and after dynamic scene perturbation tests.
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# [INTRODUCED 2026-11-28T00:13:00+08:00]
# FUNCTION: _open_playground_query
# PURPOSE: Open `output/dynamics_playground.blend` read-only in Blender memory and construct a mesh-backed `DynamicsEnvironmentQuery` scoped to `Playground_Surfaces`.
# REASON: TASK 7B-1 — Standardize T01–T12 initialization through `create_mesh_backed_dynamics_query()` with `prefer_mesh=True` and zero second playground creation.
def _open_playground_query() -> DynamicsEnvironmentQuery:
    if not os.path.isfile(PLAYGROUND_BLEND):
        raise FileNotFoundError(f"Authoritative playground blend missing: {PLAYGROUND_BLEND}")
    bpy.ops.wm.open_mainfile(filepath=PLAYGROUND_BLEND)
    bpy.context.view_layer.update()
    query = create_mesh_backed_dynamics_query(
        scene=bpy.context.scene,
        collection_names=("Playground_Surfaces",),
        prefer_mesh=True,
        ground_z=0.0,
    )
    if not query.prefer_mesh or query.mesh_adapter is None:
        raise RuntimeError("Expected mesh-backed DynamicsEnvironmentQuery with prefer_mesh=True")
    return query


# [INTRODUCED 2026-11-28T00:13:00+08:00]
# FUNCTION: _dist3
# PURPOSE: Compute Euclidean distance between two 3D vectors or tuples.
# REASON: TASK 7B-1 — Check position and rotated-normal tolerances against fixed acceptance thresholds (`<= 1e-5`).
def _dist3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


# [INTRODUCED 2026-11-28T00:13:00+08:00]
# FUNCTION: _assert_valid_mesh_hit
# PURPOSE: Validate mesh provenance, strict `surface_id` polygon format, finite world coordinates, unit surface normal tolerance, and optional expected position/normal bounds.
# REASON: TASK 7B-1 (T01–T05, T08–T10, T12) — Enforce Environment Gate 01 + 7B-1 mathematical accuracy and target identity contracts without analytical fallback.
def _assert_valid_mesh_hit(
    tc: unittest.TestCase,
    res: SurfaceQueryResult,
    expected_obj_name: str,
    expected_point: Optional[Tuple[float, float, float]] = None,
    expected_normal: Optional[Tuple[float, float, float]] = None,
) -> int:
    tc.assertTrue(res.success, f"Expected successful mesh query for {expected_obj_name}, got: {res}")
    tc.assertEqual(res.source_type, "mesh", f"Analytical/default source prohibited: {res.source_type}")
    tc.assertIsNone(res.error_reason, f"Successful query must have error_reason=None, got: {res.error_reason}")

    pattern = rf"^mesh:{re.escape(expected_obj_name)}:(\d+)$"
    m = re.match(pattern, res.surface_id)
    tc.assertIsNotNone(
        m,
        f"Expected surface_id matching 'mesh:{expected_obj_name}:<polygon_index>', got {res.surface_id!r}",
    )
    poly_idx = int(m.group(1))
    obj = bpy.data.objects.get(expected_obj_name)
    tc.assertIsNotNone(obj, f"Target Blender object missing: {expected_obj_name}")
    tc.assertGreaterEqual(poly_idx, 0)
    tc.assertLess(poly_idx, len(obj.data.polygons), "Polygon index out of range for target mesh")

    tc.assertEqual(len(res.contact_point_world), 3)
    tc.assertTrue(all(math.isfinite(c) for c in res.contact_point_world), f"Non-finite contact: {res.contact_point_world}")
    tc.assertEqual(len(res.surface_normal_world), 3)
    tc.assertTrue(all(math.isfinite(n) for n in res.surface_normal_world), f"Non-finite normal: {res.surface_normal_world}")
    tc.assertTrue(math.isfinite(res.signed_distance), f"Non-finite signed_distance: {res.signed_distance}")
    tc.assertTrue(math.isfinite(res.friction_coeff), f"Non-finite friction_coeff: {res.friction_coeff}")

    norm_len = math.sqrt(sum(n * n for n in res.surface_normal_world))
    tc.assertLessEqual(
        abs(norm_len - 1.0),
        UNIT_NORM_TOL,
        f"Normal must be unit length within {UNIT_NORM_TOL}: len={norm_len}, n={res.surface_normal_world}",
    )

    if expected_point is not None:
        pos_err = _dist3(res.contact_point_world, expected_point)
        tc.assertLessEqual(
            pos_err,
            POS_TOL_M,
            f"Position error {pos_err:.8f}m > {POS_TOL_M}m: actual={res.contact_point_world}, expected={expected_point}",
        )

    if expected_normal is not None:
        norm_err = _dist3(res.surface_normal_world, expected_normal)
        tc.assertLessEqual(
            norm_err,
            NORM_VEC_TOL,
            f"Normal error {norm_err:.8f} > {NORM_VEC_TOL}: actual={res.surface_normal_world}, expected={expected_normal}",
        )

    return poly_idx


# [INTRODUCED 2026-11-28T00:13:00+08:00]
# FUNCTION: _assert_failed_query
# PURPOSE: Verify failed queries return `success=False`, `source_type="none"`, `surface_id="none"`, and a non-empty diagnostic `error_reason`.
# REASON: TASK 7B-1 (T06, T07, T11) — Guarantee failed environmental queries never fabricate targets or silent flat-ground fallbacks.
def _assert_failed_query(tc: unittest.TestCase, res: SurfaceQueryResult, expected_prefix: str = "NO_HIT:") -> None:
    tc.assertFalse(res.success, f"Expected failed query, got success=True: {res}")
    tc.assertEqual(res.surface_id, "none", f"Failed query must report surface_id='none', got {res.surface_id!r}")
    tc.assertEqual(res.source_type, "none", f"Failed query must report source_type='none', got {res.source_type!r}")
    tc.assertIsNotNone(res.error_reason, "Failed query must preserve error_reason")
    tc.assertTrue(len(res.error_reason.strip()) > 0, "error_reason must be non-empty")
    if expected_prefix:
        tc.assertTrue(
            res.error_reason.startswith(expected_prefix),
            f"Expected error_reason starting with {expected_prefix!r}, got {res.error_reason!r}",
        )


# [INTRODUCED 2026-11-28T00:13:00+08:00]
# FUNCTION: TestTask7B1EnvironmentTargets
# PURPOSE: House the standalone T01–T12 environmental end-effector target acquisition tests for Phase 7B-1.
# REASON: TASK 7B-1 — Verify live DynamicsPlayground mesh target acquisition contracts prior to 7B-2 geometric wrist conversion.
class TestTask7B1EnvironmentTargets(unittest.TestCase):
    """Standalone TASK 7B-1 verification matrix (T01–T12)."""

    _initial_blend_sha256: str = ""

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.setUpClass
    # PURPOSE: Record initial SHA-256 of `output/dynamics_playground.blend` before any suite tests run.
    # REASON: TASK 7B-1 (T12) — Prove the source `.blend` stays byte-for-byte unmodified across all tests including temporary scene perturbations.
    @classmethod
    def setUpClass(cls) -> None:
        if not os.path.isfile(PLAYGROUND_BLEND):
            raise FileNotFoundError(f"Playground blend missing: {PLAYGROUND_BLEND}")
        cls._initial_blend_sha256 = _sha256_file(PLAYGROUND_BLEND)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.tearDownClass
    # PURPOSE: Confirm `output/dynamics_playground.blend` SHA-256 remained unchanged after the entire suite finishes.
    # REASON: TASK 7B-1 — Guard protected `.blend` asset immutability even if individual tests fail.
    @classmethod
    def tearDownClass(cls) -> None:
        final_sha = _sha256_file(PLAYGROUND_BLEND)
        if final_sha != cls._initial_blend_sha256:
            raise AssertionError(
                f"Playground blend was modified! before={cls._initial_blend_sha256} after={final_sha}"
            )

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t01_vertical_wall_directional_ray
    # PURPOSE: T01 — Verify unfiltered directional ray hits `Surface_VerticalWall` front face at Y=23.8m with outward normal `(0, -1, 0)`.
    # REASON: TASK 7B-1 T01 — Acquire real wall hand-target position and outward normal from live playground mesh.
    def test_t01_vertical_wall_directional_ray(self) -> None:
        query = _open_playground_query()
        res = query.query_spatial_surface(
            point_world=(0.0, 23.5, 1.3),
            ray_direction=(0.0, 1.0, 0.0),
            max_distance=2.0,
        )
        _assert_valid_mesh_hit(
            self,
            res,
            expected_obj_name="Surface_VerticalWall",
            expected_point=(0.0, 23.8, 1.3),
            expected_normal=(0.0, -1.0, 0.0),
        )
        self.assertIsNotNone(res.ray_hit_distance)
        self.assertLessEqual(abs(res.ray_hit_distance - 0.3), POS_TOL_M)
        self.assertLessEqual(abs(res.signed_distance - 0.3), POS_TOL_M)
        self.assertEqual(res.surface_type, SurfaceGeometryType.VERTICAL_WALL.value)
        self.assertFalse(res.allows_regular_support)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t02_vault_box_top_directional_ray
    # PURPOSE: T02 — Verify unfiltered downward directional ray hits `Surface_VaultBox` top face at Z=0.9m with outward normal `(0, 0, 1)`.
    # REASON: TASK 7B-1 T02 — Acquire real vaulting box top-surface target position and normal from live playground mesh.
    def test_t02_vault_box_top_directional_ray(self) -> None:
        query = _open_playground_query()
        res = query.query_spatial_surface(
            point_world=(0.0, 28.0, 1.2),
            ray_direction=(0.0, 0.0, -1.0),
            max_distance=2.0,
        )
        _assert_valid_mesh_hit(
            self,
            res,
            expected_obj_name="Surface_VaultBox",
            expected_point=(0.0, 28.0, 0.9),
            expected_normal=(0.0, 0.0, 1.0),
        )
        self.assertIsNotNone(res.ray_hit_distance)
        self.assertLessEqual(abs(res.ray_hit_distance - 0.3), POS_TOL_M)
        self.assertLessEqual(abs(res.signed_distance - 0.3), POS_TOL_M)
        self.assertEqual(res.surface_type, SurfaceGeometryType.BOX_TOP.value)
        self.assertTrue(res.allows_regular_support)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t03_ledge_bar_directional_ray
    # PURPOSE: T03 — Verify unfiltered upward directional ray hits `Surface_LedgeBar_Crossbar` underside at Z=2.15m with outward normal `(0, 0, -1)`.
    # REASON: TASK 7B-1 T03 — Verify crossbar target acquisition via object polygon `surface_id` without modifying mesh classifier or fabricating `LEDGE_BAR`.
    def test_t03_ledge_bar_directional_ray(self) -> None:
        query = _open_playground_query()
        res = query.query_spatial_surface(
            point_world=(0.0, 32.0, 1.95),
            ray_direction=(0.0, 0.0, 1.0),
            max_distance=2.0,
        )
        _assert_valid_mesh_hit(
            self,
            res,
            expected_obj_name="Surface_LedgeBar_Crossbar",
            expected_point=(0.0, 32.0, 2.15),
            expected_normal=(0.0, 0.0, -1.0),
        )
        self.assertIsNotNone(res.ray_hit_distance)
        self.assertLessEqual(abs(res.ray_hit_distance - 0.2), POS_TOL_M)
        self.assertLessEqual(abs(res.signed_distance - 0.2), POS_TOL_M)
        self.assertFalse(res.allows_regular_support)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t04_nearest_surface_3d_queries
    # PURPOSE: T04 — Verify `ray_direction=None` 3D nearest-surface queries resolve Wall, VaultBox, and LedgeBar closest points accurately.
    # REASON: TASK 7B-1 T04 — Validate non-directional spatial proximity queries for upper-limb reach targets.
    def test_t04_nearest_surface_3d_queries(self) -> None:
        query = _open_playground_query()

        res_wall = query.query_spatial_surface(point_world=(0.0, 23.6, 1.3), ray_direction=None, max_distance=1.0)
        _assert_valid_mesh_hit(
            self,
            res_wall,
            expected_obj_name="Surface_VerticalWall",
            expected_point=(0.0, 23.8, 1.3),
            expected_normal=(0.0, -1.0, 0.0),
        )
        self.assertIsNone(res_wall.ray_hit_distance)
        self.assertLessEqual(abs(res_wall.signed_distance - 0.2), POS_TOL_M)

        res_vault = query.query_spatial_surface(point_world=(0.0, 28.0, 1.05), ray_direction=None, max_distance=1.0)
        _assert_valid_mesh_hit(
            self,
            res_vault,
            expected_obj_name="Surface_VaultBox",
            expected_point=(0.0, 28.0, 0.9),
            expected_normal=(0.0, 0.0, 1.0),
        )
        self.assertIsNone(res_vault.ray_hit_distance)
        self.assertLessEqual(abs(res_vault.signed_distance - 0.15), POS_TOL_M)

        res_ledge = query.query_spatial_surface(point_world=(0.0, 32.0, 2.02), ray_direction=None, max_distance=1.0)
        _assert_valid_mesh_hit(
            self,
            res_ledge,
            expected_obj_name="Surface_LedgeBar_Crossbar",
            expected_point=(0.0, 32.0, 2.15),
            expected_normal=(0.0, 0.0, -1.0),
        )
        self.assertIsNone(res_ledge.ray_hit_distance)
        self.assertLessEqual(abs(res_ledge.signed_distance - 0.13), POS_TOL_M)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t05_identity_provenance_and_normal_contract
    # PURPOSE: T05 — Verify `surface_id`, `source_type="mesh"`, tracked collection isolation, unit normal accuracy, and classifier boundary on all target obstacles.
    # REASON: TASK 7B-1 T05 — Confirm authentic mesh provenance, valid polygon indices, support flags, and unmodified LedgeBar classifier behavior.
    def test_t05_identity_provenance_and_normal_contract(self) -> None:
        query = _open_playground_query()
        adapter = query.mesh_adapter
        assert adapter is not None

        tracked = set(adapter.tracked_objects)
        for obj_name in ("Surface_VerticalWall", "Surface_VaultBox", "Surface_LedgeBar_Crossbar"):
            self.assertIn(obj_name, tracked, f"Required obstacle missing from Playground_Surfaces: {obj_name}")
        # Ensure non-surface visuals collection is strictly excluded
        self.assertNotIn("Debug_1m_UnitCube", tracked)

        samples = [
            ("Surface_VerticalWall", (0.0, 23.5, 1.3), (0.0, 1.0, 0.0), (0.0, 23.8, 1.3), (0.0, -1.0, 0.0), False, SurfaceGeometryType.VERTICAL_WALL.value),
            ("Surface_VaultBox", (0.0, 28.0, 1.2), (0.0, 0.0, -1.0), (0.0, 28.0, 0.9), (0.0, 0.0, 1.0), True, SurfaceGeometryType.BOX_TOP.value),
            ("Surface_LedgeBar_Crossbar", (0.0, 32.0, 1.95), (0.0, 0.0, 1.0), (0.0, 32.0, 2.15), (0.0, 0.0, -1.0), False, SurfaceGeometryType.VERTICAL_WALL.value),
        ]
        valid_enum_values = {m.value for m in SurfaceGeometryType}
        for obj_name, origin, direction, exp_pt, exp_n, exp_support, exp_type in samples:
            res = query.query_spatial_surface(origin, direction, max_distance=2.0)
            poly_idx = _assert_valid_mesh_hit(self, res, obj_name, exp_pt, exp_n)
            self.assertEqual(res.surface_id, f"mesh:{obj_name}:{poly_idx}")
            self.assertIn(res.surface_type, valid_enum_values)
            self.assertEqual(res.surface_type, exp_type)
            self.assertEqual(res.allows_regular_support, exp_support)
            self.assertGreater(res.friction_coeff, 0.0)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t06_insufficient_max_distance_fails
    # PURPOSE: T06 — Verify both directional ray and nearest-point queries fail cleanly when `max_distance` falls short of the true target.
    # REASON: TASK 7B-1 T06 — Ensure short-range queries report genuine `NO_HIT` failure rather than returning analytical or out-of-range targets.
    def test_t06_insufficient_max_distance_fails(self) -> None:
        query = _open_playground_query()

        res_wall_ray = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=0.2)
        _assert_failed_query(self, res_wall_ray, expected_prefix="NO_HIT:")

        res_box_ray = query.query_spatial_surface((0.0, 28.0, 1.2), (0.0, 0.0, -1.0), max_distance=0.2)
        _assert_failed_query(self, res_box_ray, expected_prefix="NO_HIT:")

        res_bar_ray = query.query_spatial_surface((0.0, 32.0, 1.95), (0.0, 0.0, 1.0), max_distance=0.1)
        _assert_failed_query(self, res_bar_ray, expected_prefix="NO_HIT:")

        res_wall_near = query.query_spatial_surface((0.0, 23.5, 1.3), ray_direction=None, max_distance=0.2)
        _assert_failed_query(self, res_wall_near, expected_prefix="NO_HIT:")

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t07_ray_miss_fails_honestly
    # PURPOSE: T07 — Verify directional rays pointing into open empty space fail with `NO_HIT:` and never fall back to analytical surfaces.
    # REASON: TASK 7B-1 T07 — Enforce zero-hallucination failure reporting on genuine geometric misses.
    def test_t07_ray_miss_fails_honestly(self) -> None:
        query = _open_playground_query()

        res_away = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, -1.0, 0.0), max_distance=4.0)
        _assert_failed_query(self, res_away, expected_prefix="NO_HIT:")

        res_sky = query.query_spatial_surface((0.0, 23.5, 5.0), (0.0, 0.0, 1.0), max_distance=10.0)
        _assert_failed_query(self, res_sky, expected_prefix="NO_HIT:")

        res_void = query.query_spatial_surface((0.0, 30.5, -2.0), (0.0, 0.0, -1.0), max_distance=10.0)
        _assert_failed_query(self, res_void, expected_prefix="NO_HIT:")

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t08_occlusion_returns_first_hit_no_penetration
    # PURPOSE: T08 — Move `Surface_VaultBox` in-memory cleanly in front of `Surface_VerticalWall` and confirm unfiltered raycast stops at the occluder without penetrating to the rear wall.
    # REASON: TASK 7B-1 T08 — Prove first-hit occlusion fidelity on the existing cache-refreshed BVH adapter.
    def test_t08_occlusion_returns_first_hit_no_penetration(self) -> None:
        query = _open_playground_query()
        adapter = query.mesh_adapter
        assert adapter is not None
        rebuilds_before = adapter.rebuild_count

        # VaultBox local bounds: Y in [26.5, 29.5], Z in [0.0, 0.90].
        # Shifting by (0.0, -6.0, 0.6) places VaultBox cleanly at Y in [20.5, 23.5], Z in [0.6, 1.5],
        # strictly occluding Surface_VerticalWall (Y in [23.8, 24.2]) along +Y at Z=1.3.
        vault_box = bpy.data.objects["Surface_VaultBox"]
        vault_box.location = Vector((0.0, -6.0, 0.6))
        bpy.context.view_layer.update()

        res = query.query_spatial_surface(
            point_world=(0.0, 19.5, 1.3),
            ray_direction=(0.0, 1.0, 0.0),
            max_distance=6.0,
        )
        self.assertGreater(adapter.rebuild_count, rebuilds_before, "Transform change must trigger BVH rebuild via refresh()")
        _assert_valid_mesh_hit(
            self,
            res,
            expected_obj_name="Surface_VaultBox",
            expected_point=(0.0, 20.5, 1.3),
            expected_normal=(0.0, -1.0, 0.0),
        )
        self.assertNotIn("Surface_VerticalWall", res.surface_id)
        self.assertLessEqual(abs(res.ray_hit_distance - 1.0), POS_TOL_M)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t09_environment_translation_updates_target
    # PURPOSE: T09 — Translate `Surface_VerticalWall` in-memory and verify the same `query` instance returns the shifted world target without recreating the adapter.
    # REASON: TASK 7B-1 T09 — Verify live depsgraph/matrix change detection updates environmental hand-target positions.
    def test_t09_environment_translation_updates_target(self) -> None:
        query = _open_playground_query()
        adapter = query.mesh_adapter
        assert adapter is not None

        res_orig = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        _assert_valid_mesh_hit(self, res_orig, "Surface_VerticalWall", (0.0, 23.8, 1.3), (0.0, -1.0, 0.0))
        rebuilds_before = adapter.rebuild_count

        wall = bpy.data.objects["Surface_VerticalWall"]
        wall.location = Vector((0.25, -0.45, 0.30))
        bpy.context.view_layer.update()

        res_shifted = query.query_spatial_surface((0.0, 23.0, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        self.assertEqual(adapter.rebuild_count, rebuilds_before + 1, "Single translation should trigger exactly 1 BVH rebuild")
        _assert_valid_mesh_hit(
            self,
            res_shifted,
            expected_obj_name="Surface_VerticalWall",
            expected_point=(0.0, 23.35, 1.3),
            expected_normal=(0.0, -1.0, 0.0),
        )
        self.assertLessEqual(abs(res_shifted.ray_hit_distance - 0.35), POS_TOL_M)
        self.assertGreater(_dist3(res_shifted.contact_point_world, res_orig.contact_point_world), 0.40)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t10_environment_rotation_updates_position_and_normal
    # PURPOSE: T10 — Rotate `Surface_VerticalWall` in-memory and verify the queried world position and normal match `M @ p` and `R @ n_original` within `1e-5`.
    # REASON: TASK 7B-1 T10 — Verify 3D world-space normal transformation accuracy on rotated playground obstacles.
    def test_t10_environment_rotation_updates_position_and_normal(self) -> None:
        query = _open_playground_query()
        adapter = query.mesh_adapter
        assert adapter is not None

        res_orig = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        _assert_valid_mesh_hit(self, res_orig, "Surface_VerticalWall", (0.0, 23.8, 1.3), (0.0, -1.0, 0.0))
        rebuilds_before = adapter.rebuild_count

        wall = bpy.data.objects["Surface_VerticalWall"]
        wall.rotation_euler = Euler((math.radians(10.0), 0.0, math.radians(30.0)), "XYZ")
        bpy.context.view_layer.update()

        mat_w: Matrix = wall.matrix_world.copy()
        rot_3x3 = mat_w.to_3x3().normalized()
        p_expected_vec = mat_w @ Vector((0.0, 23.8, 1.3))
        n_expected_vec = (rot_3x3 @ Vector((0.0, -1.0, 0.0))).normalized()
        self.assertLess(n_expected_vec.z, 0.50)

        ray_origin = p_expected_vec + 0.35 * n_expected_vec
        ray_dir = -n_expected_vec
        res_rot = query.query_spatial_surface(
            point_world=(ray_origin.x, ray_origin.y, ray_origin.z),
            ray_direction=(ray_dir.x, ray_dir.y, ray_dir.z),
            max_distance=1.0,
        )
        self.assertEqual(adapter.rebuild_count, rebuilds_before + 1)
        _assert_valid_mesh_hit(
            self,
            res_rot,
            expected_obj_name="Surface_VerticalWall",
            expected_point=(p_expected_vec.x, p_expected_vec.y, p_expected_vec.z),
            expected_normal=(n_expected_vec.x, n_expected_vec.y, n_expected_vec.z),
        )
        self.assertFalse(res_rot.allows_regular_support)
        self.assertLessEqual(abs(res_rot.ray_hit_distance - 0.35), POS_TOL_M)

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t11_unlinked_object_evicted_from_cache
    # PURPOSE: T11 — Unlink `Surface_VerticalWall` from `Playground_Surfaces` and verify the existing adapter rebuilds and does not return stale cached hits.
    # REASON: TASK 7B-1 T11 — Prove collection-membership cache invalidation rejects removed obstacles without recreating the adapter.
    def test_t11_unlinked_object_evicted_from_cache(self) -> None:
        query = _open_playground_query()
        adapter = query.mesh_adapter
        assert adapter is not None

        res_before = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        _assert_valid_mesh_hit(self, res_before, "Surface_VerticalWall", (0.0, 23.8, 1.3), (0.0, -1.0, 0.0))
        rebuilds_before = adapter.rebuild_count

        col = bpy.data.collections["Playground_Surfaces"]
        wall = bpy.data.objects["Surface_VerticalWall"]
        col.objects.unlink(wall)
        bpy.context.view_layer.update()

        res_after = query.query_spatial_surface((0.0, 23.5, 1.3), (0.0, 1.0, 0.0), max_distance=2.0)
        self.assertEqual(adapter.rebuild_count, rebuilds_before + 1, "Unlinking collection member must trigger rebuild")
        self.assertNotIn("Surface_VerticalWall", adapter.tracked_objects)
        _assert_failed_query(self, res_after, expected_prefix="NO_HIT:")

    # [INTRODUCED 2026-11-28T00:13:00+08:00]
    # FUNCTION: TestTask7B1EnvironmentTargets.test_t12_source_blend_integrity_and_repeat_consistency
    # PURPOSE: T12 — Verify source `.blend` SHA-256 immutability and deterministic zero-rebuild repeat consistency across Wall, VaultBox, and LedgeBar queries.
    # REASON: TASK 7B-1 T12 — Confirm repeated queries on an unchanged scene reuse the compiled BVH with zero drift or file mutation.
    def test_t12_source_blend_integrity_and_repeat_consistency(self) -> None:
        self.assertEqual(_sha256_file(PLAYGROUND_BLEND), self._initial_blend_sha256)
        query = _open_playground_query()
        adapter = query.mesh_adapter
        assert adapter is not None

        probes = [
            ("Surface_VerticalWall", (0.0, 23.5, 1.3), (0.0, 1.0, 0.0), (0.0, 23.8, 1.3), (0.0, -1.0, 0.0)),
            ("Surface_VaultBox", (0.0, 28.0, 1.2), (0.0, 0.0, -1.0), (0.0, 28.0, 0.9), (0.0, 0.0, 1.0)),
            ("Surface_LedgeBar_Crossbar", (0.0, 32.0, 1.95), (0.0, 0.0, 1.0), (0.0, 32.0, 2.15), (0.0, 0.0, -1.0)),
        ]
        baselines = []
        for obj_name, origin, direction, exp_pt, exp_n in probes:
            r0 = query.query_spatial_surface(origin, direction, max_distance=2.0)
            _assert_valid_mesh_hit(self, r0, obj_name, exp_pt, exp_n)
            baselines.append(r0)

        rebuilds_after_init = adapter.rebuild_count
        for _ in range(5):
            for idx, (obj_name, origin, direction, exp_pt, exp_n) in enumerate(probes):
                r_rep = query.query_spatial_surface(origin, direction, max_distance=2.0)
                _assert_valid_mesh_hit(self, r_rep, obj_name, exp_pt, exp_n)
                self.assertEqual(r_rep, baselines[idx], f"Repeated unchanged query drifted on {obj_name}")

        self.assertEqual(adapter.rebuild_count, rebuilds_after_init, "Unchanged scene queries must perform zero extra rebuilds")
        self.assertEqual(_sha256_file(PLAYGROUND_BLEND), self._initial_blend_sha256)


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1 :])
    unittest.main(argv=argv, verbosity=2)
