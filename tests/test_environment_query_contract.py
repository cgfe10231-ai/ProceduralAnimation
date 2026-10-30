"""ProceduralAnimation — Targeted Test Suite for Part 1: Unified Environment Query Contract (FIND-R4-02).

Validates the environment query contract across:
1. Real Mesh hits valid ground.
2. Mesh raycast misses (empty air / off-mesh).
3. Mesh hits non-support surface (steep slope exceeding max support slope).
4. Mesh hits vertical wall.
5. Consistency between ground_height_at and surface_normal_at at the same coordinates.
6. Pure analytical environment default flat ground lawful behavior.
7. DynamicsEnvironmentQuery without mesh adapter compatibility.
8. EnvironmentQuery.query_ground_support_at failure when allows_regular_support is False.
"""

from __future__ import annotations

import math
import os
import sys
import unittest

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy

from src.scene.blender_mesh_query_adapter import (
    BlenderMeshEnvironmentAdapter,
    create_mesh_backed_dynamics_query,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    EnvironmentQuery,
    OrientedSurface,
    SurfaceGeometryType,
    SurfaceQueryResult,
)


class TestEnvironmentQueryContract(unittest.TestCase):
    """Targeted regression test for FIND-R4-02: Unified Environment Query Contract."""

    @classmethod
    def setUpClass(cls) -> None:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene

        col = bpy.data.collections.new("TestSurfaces")
        scene.collection.children.link(col)

        # 1. Flat horizontal ground at Z = 1.0, size 4x4 (X: -2..2, Y: -2..2)
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 1.0))
        flat_plane = bpy.context.active_object
        flat_plane.name = "Test_FlatPlane"
        col.objects.link(flat_plane)

        # 2. Vertical wall at X = 5.0, Y: -2..2, Z: 0..4 (Normal: (-1, 0, 0))
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(5.0, 0.0, 2.0))
        vert_wall = bpy.context.active_object
        vert_wall.name = "Test_VerticalWall"
        vert_wall.rotation_euler = (0.0, math.radians(90.0), 0.0)
        col.objects.link(vert_wall)

        # 3. Steep non-support slope (60 degrees, exceeds standard ~35 deg max walkable slope) at X = -5.0
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(-5.0, 0.0, 2.0))
        steep_slope = bpy.context.active_object
        steep_slope.name = "Test_SteepSlope"
        steep_slope.rotation_euler = (0.0, math.radians(60.0), 0.0)
        col.objects.link(steep_slope)

        bpy.context.view_layer.update()

        cls.adapter = BlenderMeshEnvironmentAdapter(
            scene=scene,
            collection_names=("TestSurfaces",),
            min_support_normal_z=math.cos(math.radians(35.0)),
        )
        cls.mesh_env = DynamicsEnvironmentQuery(ground_z=0.0)
        cls.mesh_env.set_mesh_adapter(cls.adapter, prefer_mesh=True)

    def test_01_real_mesh_hit_valid_ground(self) -> None:
        """1. Real Mesh hits valid walkable ground."""
        res = self.mesh_env.query_ground_support_at(0.0, 0.0)
        self.assertTrue(res.success, "Query on valid plane should succeed")
        self.assertTrue(res.allows_regular_support, "Flat plane should allow regular support")
        self.assertAlmostEqual(res.contact_point_world[2], 1.0, places=3)
        self.assertEqual(res.source_type, "mesh")

        # 2.5D queries
        h = self.mesh_env.ground_height_at(0.0, 0.0)
        self.assertIsNotNone(h)
        self.assertAlmostEqual(h, 1.0, places=3)

        n = self.mesh_env.surface_normal_at(0.0, 0.0)
        self.assertIsNotNone(n)
        self.assertAlmostEqual(n[0], 0.0, places=3)
        self.assertAlmostEqual(n[1], 0.0, places=3)
        self.assertAlmostEqual(n[2], 1.0, places=3)

    def test_02_mesh_raycast_miss(self) -> None:
        """2. Mesh raycast misses (empty space / off-mesh coordinate).
        Must NOT fake ground_z (0.0) or world-up normal (0, 0, 1).
        """
        # Coordinate (20.0, 20.0) has no mesh
        res = self.mesh_env.query_ground_support_at(20.0, 20.0)
        self.assertFalse(res.success, "Off-mesh query must report success=False")
        self.assertFalse(res.allows_regular_support, "Off-mesh query must report allows_regular_support=False")
        self.assertIn("NO_HIT", res.error_reason or "")

        # 2.5D query: must NOT fake 0.0m elevation
        h = self.mesh_env.ground_height_at(20.0, 20.0)
        self.assertIsNone(h, "ground_height_at must return None on mesh miss instead of faking ground_z=0.0")

        # 2.5D normal: must NOT fake (0, 0, 1) normal
        n = self.mesh_env.surface_normal_at(20.0, 20.0)
        self.assertIsNone(n, "surface_normal_at must return None on mesh miss instead of faking (0, 0, 1)")

    def test_03_mesh_hit_non_support_surface(self) -> None:
        """3. Mesh hits non-support surface (steep slope 60 deg > 35 deg).
        Must report allows_regular_support=False, success=False, and 2.5D queries must return None.
        """
        res = self.mesh_env.query_ground_support_at(-5.0, 0.0)
        self.assertFalse(res.success, "Steep non-support slope must report success=False")
        self.assertFalse(res.allows_regular_support, "Steep slope must report allows_regular_support=False")
        self.assertIn("NON_SUPPORT_SURFACE", res.error_reason or "")

        h = self.mesh_env.ground_height_at(-5.0, 0.0)
        self.assertIsNone(h, "ground_height_at must return None on non-support surface")

        n = self.mesh_env.surface_normal_at(-5.0, 0.0)
        self.assertIsNone(n, "surface_normal_at must return None on non-support surface")

    def test_04_mesh_hit_vertical_wall(self) -> None:
        """4. Mesh hits vertical wall.
        Must report allows_regular_support=False, success=False, and 2.5D queries must return None.
        """
        # The vertical wall is at X = 5.0, spanning Y: -2..2, Z: 0..4
        # A downward ray at X = 5.0 will hit the wall surface/edge
        # Also check adapter.surface_normal_at directly
        adapter_norm = self.adapter.surface_normal_at(5.0, 0.0)
        self.assertIsNone(
            adapter_norm,
            "adapter.surface_normal_at must return None when hitting non-support vertical wall",
        )

        h = self.mesh_env.ground_height_at(5.0, 0.0)
        self.assertIsNone(h, "ground_height_at must return None when hitting non-support vertical wall")

        n = self.mesh_env.surface_normal_at(5.0, 0.0)
        self.assertIsNone(n, "surface_normal_at must return None when hitting non-support vertical wall")

    def test_05_consistency_height_and_normal(self) -> None:
        """5. Consistency between height query and normal query at the same coordinates.
        Never split spatial semantics: if height is None, normal MUST be None;
        if height is valid, normal MUST be valid.
        """
        test_coords = [
            (0.0, 0.0),    # Hit valid ground
            (20.0, 20.0),  # Void / Miss
            (-5.0, 0.0),   # Steep slope
            (5.0, 0.0),    # Vertical wall
            (1.0, 1.0),    # Hit valid ground
            (-20.0, 0.0),  # Void / Miss
        ]
        for x, y in test_coords:
            h = self.mesh_env.ground_height_at(x, y)
            n = self.mesh_env.surface_normal_at(x, y)
            if h is None:
                self.assertIsNone(
                    n,
                    f"Spatial inconsistency at ({x}, {y}): ground_height_at is None but surface_normal_at is {n}",
                )
            else:
                self.assertIsNotNone(
                    n,
                    f"Spatial inconsistency at ({x}, {y}): ground_height_at is {h} but surface_normal_at is None",
                )

    def test_06_pure_analytical_environment_flat_ground(self) -> None:
        """6. Pure analytical environment default flat ground lawful behavior."""
        base_env = EnvironmentQuery(ground_z=0.0)
        res = base_env.query_ground_support_at(12.3, 45.6)
        self.assertTrue(res.success)
        self.assertTrue(res.allows_regular_support)
        self.assertAlmostEqual(res.contact_point_world[2], 0.0, places=3)
        self.assertEqual(res.source_type, "default")
        self.assertAlmostEqual(base_env.ground_height_at(12.3, 45.6), 0.0, places=3)
        self.assertEqual(base_env.surface_normal_at(12.3, 45.6), (0.0, 0.0, 1.0))

    def test_07_dynamics_query_without_mesh_adapter(self) -> None:
        """7. DynamicsEnvironmentQuery without mesh adapter (pure analytical mode)."""
        dyn_env = DynamicsEnvironmentQuery(ground_z=0.0)
        res = dyn_env.query_ground_support_at(3.0, 4.0)
        self.assertTrue(res.success)
        self.assertTrue(res.allows_regular_support)
        self.assertAlmostEqual(res.contact_point_world[2], 0.0, places=3)
        self.assertEqual(res.source_type, "analytical")
        self.assertAlmostEqual(dyn_env.ground_height_at(3.0, 4.0), 0.0, places=3)
        self.assertEqual(dyn_env.surface_normal_at(3.0, 4.0), (0.0, 0.0, 1.0))

    def test_08_base_query_ground_support_rejection(self) -> None:
        """8. EnvironmentQuery.query_ground_support_at must return success=False when allows_regular_support is False."""
        class MockNonSupportBaseQuery(EnvironmentQuery):
            def query_surface_at_point(self, point_world, max_distance=5.0, surface_type_filter=None):
                return SurfaceQueryResult(
                    surface_id="steep_cliff",
                    surface_type="cliff",
                    contact_point_world=point_world,
                    surface_normal_world=(0.0, 0.0, 1.0),
                    signed_distance=0.0,
                    friction_coeff=0.0,
                    allows_regular_support=False,
                    success=True,
                    ray_hit_distance=None,
                    error_reason="NON_SUPPORT_SURFACE: Cliff exceeds maximum support angle",
                )

        env_non_support = MockNonSupportBaseQuery(ground_z=0.0)
        res = env_non_support.query_ground_support_at(0.0, 0.0)
        self.assertFalse(res.allows_regular_support)
        self.assertFalse(res.success, "query_ground_support_at must NOT return success=True when allows_regular_support=False")
        self.assertIsNotNone(res.error_reason)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
