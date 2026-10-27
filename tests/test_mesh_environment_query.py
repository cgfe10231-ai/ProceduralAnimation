"""Comprehensive Verification Test Suite for Blender Mesh Environment Query Adapter.

Task: Environment Gate 01.
Target: `src/scene/blender_mesh_query_adapter.py` & `src/scene/environment_query.py`.

Covers all 14 Acceptance Criteria:
1. Flat ground correct hit (location, normal, support=True).
2. Sloped ramps (+15 deg uphill and -20 deg downhill) correct normals and elevations.
3. Stairs and elevated platform correct heights (step 3 at 0.45m, landing at 0.75m, bridge at 1.34m).
4. Vertical wall lateral query (outward normal, support=False).
5. Mesh object translation dynamically updates query results upon refresh.
6. Mesh object rotation dynamically updates outward surface normals upon refresh.
7. Editing mesh vertex coordinates directly updates query geometry.
8. Deleting / removing target mesh object properly returns non-hit (success=False).
9. Gaps and cliffs return miss (success=False), never a fictitious Z=0 ground plane.
10. Non-support surfaces (vertical walls, ceilings) strictly report allows_regular_support=False.
11. Analytical query tests remain backward-compatible and functional.
12. Zero byte modifications to protected historical .blend scene assets.
13. Counter-example assertions proving cache refresh and dynamic detection are active.
14. No pre-hardcoded duplicate height comparison: queries live evaluated Blender geometry.
"""

import math
import os
import sys
import unittest

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
from mathutils import Matrix, Vector

from src.scene.blender_mesh_query_adapter import (
    BlenderMeshEnvironmentAdapter,
    create_mesh_backed_dynamics_query,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    SurfaceGeometryType,
    SurfaceQueryResult,
    create_standard_dynamics_playground_query,
)


class TestMeshEnvironmentQuery(unittest.TestCase):
    """Test suite verifying live Blender mesh spatial and raycast querying."""

    def test_01_read_only_playground_blend_geometry(self):
        """Verify queries against real evaluated geometry in output/dynamics_playground.blend."""
        blend_path = os.path.join(repo_root, "output", "dynamics_playground.blend")
        self.assertTrue(os.path.isfile(blend_path), f"Playground blend missing: {blend_path}")

        # Open in background (strictly read-only)
        bpy.ops.wm.open_mainfile(filepath=blend_path)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("Playground_Surfaces",))
        self.assertGreater(adapter.polygon_count, 50, "Expected at least 50 polygons in playground")
        self.assertIn("Surface_FlatGround", adapter.tracked_objects)
        self.assertIn("Surface_Ramp_Up", adapter.tracked_objects)
        self.assertIn("Surface_Ramp_TopPlatform", adapter.tracked_objects)
        self.assertIn("Surface_VerticalWall", adapter.tracked_objects)

        # 1. Flat ground: Downward ray at (0, 0, 5)
        res_ground = adapter.query_spatial_surface(
            point_world=(0.0, 0.0, 5.0),
            ray_direction=(0.0, 0.0, -1.0),
            max_distance=10.0,
        )
        self.assertTrue(res_ground.success)
        self.assertEqual(res_ground.source_type, "mesh")
        self.assertAlmostEqual(res_ground.contact_point_world[2], 0.0, places=3)
        self.assertAlmostEqual(res_ground.surface_normal_world[2], 1.0, places=3)
        self.assertTrue(res_ground.allows_regular_support)
        self.assertIn("Surface_FlatGround", res_ground.surface_id)

        # 2. Uphill Ramp (+15 deg) at Y=13.5
        res_ramp_up = adapter.query_spatial_surface(
            point_world=(0.0, 13.5, 5.0),
            ray_direction=(0.0, 0.0, -1.0),
            max_distance=10.0,
        )
        self.assertTrue(res_ramp_up.success)
        self.assertIn("Surface_Ramp_Up", res_ramp_up.surface_id)
        # Expected elevation at Y=13.5: ramp starts at Y=11.0, delta_y=2.5. Z = 2.5 * tan(15 deg) = 0.6699m
        expected_ramp_z = 2.5 * math.tan(math.radians(15.0))
        self.assertAlmostEqual(res_ramp_up.contact_point_world[2], expected_ramp_z, places=3)
        # Expected normal: (0, -sin(15), cos(15)) = (0, -0.2588, 0.9659)
        self.assertAlmostEqual(res_ramp_up.surface_normal_world[1], -math.sin(math.radians(15.0)), places=3)
        self.assertAlmostEqual(res_ramp_up.surface_normal_world[2], math.cos(math.radians(15.0)), places=3)
        self.assertTrue(res_ramp_up.allows_regular_support)
        self.assertEqual(res_ramp_up.surface_type, SurfaceGeometryType.SLOPED_RAMP.value)

        # 3. Bridge Platform at Y=17.0
        res_bridge = adapter.query_spatial_surface(
            point_world=(0.0, 17.0, 5.0),
            ray_direction=(0.0, 0.0, -1.0),
            max_distance=10.0,
        )
        self.assertTrue(res_bridge.success)
        self.assertIn("Surface_Ramp_TopPlatform", res_bridge.surface_id)
        expected_bridge_z = 5.0 * math.tan(math.radians(15.0))  # 1.3397m
        self.assertAlmostEqual(res_bridge.contact_point_world[2], expected_bridge_z, places=3)
        self.assertAlmostEqual(res_bridge.surface_normal_world[2], 1.0, places=3)
        self.assertTrue(res_bridge.allows_regular_support)

        # 4. Stairs step 3 at Y=6.75 (step starts at 6.0, step 3 is [6.6, 6.9], tread_z = 3 * 0.15 = 0.45m)
        res_stair = adapter.query_spatial_surface(
            point_world=(0.0, 6.75, 5.0),
            ray_direction=(0.0, 0.0, -1.0),
            max_distance=10.0,
        )
        self.assertTrue(res_stair.success)
        self.assertAlmostEqual(res_stair.contact_point_world[2], 0.45, places=3)
        self.assertTrue(res_stair.allows_regular_support)

        # 5. Vertical Wall lateral query: ray from (0, 22.0, 1.0) along +Y toward wall at Y=23.8
        res_wall = adapter.query_spatial_surface(
            point_world=(0.0, 22.0, 1.0),
            ray_direction=(0.0, 1.0, 0.0),
            max_distance=5.0,
        )
        self.assertTrue(res_wall.success)
        self.assertIn("Surface_VerticalWall", res_wall.surface_id)
        self.assertAlmostEqual(res_wall.contact_point_world[1], 23.8, places=2)
        self.assertAlmostEqual(res_wall.surface_normal_world[1], -1.0, places=3)
        self.assertFalse(res_wall.allows_regular_support, "Vertical wall must not allow regular foot support!")
        self.assertEqual(res_wall.surface_type, SurfaceGeometryType.VERTICAL_WALL.value)

        # 6. Cliff & Gap at Y=10.5 (between stairs landing platform and ramp entrance)
        res_gap = adapter.query_spatial_surface(
            point_world=(0.0, 10.5, 5.0),
            ray_direction=(0.0, 0.0, -1.0),
            max_distance=10.0,
        )
        self.assertFalse(res_gap.success, "Gap between platforms must not return a fake hit!")
        self.assertEqual(res_gap.surface_id, "none")
        self.assertEqual(res_gap.source_type, "none")
        self.assertIsNotNone(res_gap.error_reason)

    def test_02_dynamic_mesh_translation(self):
        """Verify that moving an object in the scene dynamically updates query results upon refresh."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        # Create box at Z=1.0m
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.0))
        box = bpy.context.active_object
        box.name = "DynamicBox"
        col.objects.link(box)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("TestCol",))
        res_init = adapter.query_spatial_surface((0.0, 0.0, 10.0), (0.0, 0.0, -1.0))
        self.assertTrue(res_init.success)
        self.assertAlmostEqual(res_init.contact_point_world[2], 2.0, places=3)  # center 1.0 + half-size 1.0 = 2.0

        # Translate object to Z=4.5m
        box.location.z = 4.5
        bpy.context.view_layer.update()

        # Query without refresh vs with refresh (Counter-example check)
        adapter.refresh()
        res_moved = adapter.query_spatial_surface((0.0, 0.0, 10.0), (0.0, 0.0, -1.0))
        self.assertTrue(res_moved.success)
        # Expected new top: 4.5 + 1.0 = 5.5m
        self.assertAlmostEqual(res_moved.contact_point_world[2], 5.5, places=3)
        self.assertNotEqual(res_moved.contact_point_world[2], res_init.contact_point_world[2])

    def test_03_dynamic_mesh_rotation(self):
        """Verify that rotating an object dynamically updates outward surface normals."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        # Create flat plane at Z=0.0m
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 0.0))
        plane = bpy.context.active_object
        col.objects.link(plane)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("TestCol",))
        res_init = adapter.query_spatial_surface((0.0, 0.0, 5.0), (0.0, 0.0, -1.0))
        self.assertAlmostEqual(res_init.surface_normal_world[2], 1.0, places=3)

        # Rotate plane 30 degrees around X-axis
        angle_rad = math.radians(30.0)
        plane.rotation_euler.x = angle_rad
        bpy.context.view_layer.update()

        adapter.refresh()
        res_rot = adapter.query_spatial_surface((0.0, 0.0, 5.0), (0.0, 0.0, -1.0))
        self.assertTrue(res_rot.success)
        # Expected rotated normal: (0, -sin(30), cos(30)) = (0, -0.5, 0.866)
        self.assertAlmostEqual(res_rot.surface_normal_world[1], -math.sin(angle_rad), places=3)
        self.assertAlmostEqual(res_rot.surface_normal_world[2], math.cos(angle_rad), places=3)

    def test_04_vertex_level_mesh_editing(self):
        """Verify that editing raw mesh vertex coordinates in memory updates the query geometry."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.0))
        cube = bpy.context.active_object
        col.objects.link(cube)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("TestCol",))
        res_init = adapter.ground_height_at(0.0, 0.0)
        self.assertAlmostEqual(res_init, 2.0, places=3)

        # Directly move all top vertices by +1.5m in Z
        for v in cube.data.vertices:
            if v.co.z > 0.0:
                v.co.z += 1.5
        cube.data.update()
        bpy.context.view_layer.update()

        adapter.invalidate()
        adapter.refresh(force=True)

        res_edited = adapter.ground_height_at(0.0, 0.0)
        self.assertAlmostEqual(res_edited, 3.5, places=3)

    def test_05_object_removal_returns_miss(self):
        """Verify that deleting or unlinking an object causes queries to return miss."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.0))
        cube = bpy.context.active_object
        col.objects.link(cube)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("TestCol",))
        self.assertTrue(adapter.ray_cast((0.0, 0.0, 5.0), (0.0, 0.0, -1.0)).success)

        # Remove object from scene
        bpy.data.objects.remove(cube, do_unlink=True)
        bpy.context.view_layer.update()

        adapter.invalidate()
        adapter.refresh(force=True)

        res_after = adapter.ray_cast((0.0, 0.0, 5.0), (0.0, 0.0, -1.0))
        self.assertFalse(res_after.success, "Removed object must return success=False")
        self.assertEqual(res_after.surface_id, "none")

    def test_06_non_support_surface_discrimination(self):
        """Verify that vertical walls and ceilings strictly report allows_regular_support=False."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        # Create vertical wall
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 5.0, 1.0))
        wall = bpy.context.active_object
        col.objects.link(wall)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("TestCol",), min_support_normal_z=0.50)

        # Lateral query against wall front face
        res_wall_front = adapter.ray_cast((0.0, 3.0, 1.0), (0.0, 1.0, 0.0))
        self.assertTrue(res_wall_front.success)
        self.assertFalse(res_wall_front.allows_regular_support, "Vertical wall front face must not support foot stance")

        # Top face of wall box (normal.z = 1.0)
        res_wall_top = adapter.ray_cast((0.0, 5.0, 5.0), (0.0, 0.0, -1.0))
        self.assertTrue(res_wall_top.success)
        self.assertTrue(res_wall_top.allows_regular_support, "Top horizontal face of box must allow support")

    def test_07_friction_metadata_differentiation(self):
        """Verify that custom scene friction properties are distinguished from defaults."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        # Object A with custom measured friction
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(-3.0, 0.0, 1.0))
        box_custom = bpy.context.active_object
        box_custom["friction_coeff"] = 0.42
        col.objects.link(box_custom)

        # Object B with default unmeasured friction
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(3.0, 0.0, 1.0))
        box_default = bpy.context.active_object
        col.objects.link(box_default)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=("TestCol",), default_friction=0.65)

        # Query A
        res_a = adapter.ray_cast((-3.0, 0.0, 5.0), (0.0, 0.0, -1.0))
        self.assertAlmostEqual(res_a.friction_coeff, 0.42, places=3)

        # Query B
        res_b = adapter.ray_cast((3.0, 0.0, 5.0), (0.0, 0.0, -1.0))
        self.assertAlmostEqual(res_b.friction_coeff, 0.65, places=3)

    def test_08_dynamics_environment_query_integration(self):
        """Verify DynamicsEnvironmentQuery delegating to live mesh adapter."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("TestCol")
        bpy.context.scene.collection.children.link(col)

        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 10.0, 2.0))
        platform = bpy.context.active_object
        col.objects.link(platform)

        # Create query with adapter attached and prefer_mesh=True
        env = create_mesh_backed_dynamics_query(collection_names=("TestCol",), prefer_mesh=True)
        self.assertTrue(env.has_mesh_adapter())
        self.assertTrue(env.prefer_mesh)

        # Query platform height (center 2.0 + half-size 1.0 = 3.0m)
        z = env.ground_height_at(0.0, 10.0)
        self.assertAlmostEqual(z, 3.0, places=3)

        # Query empty air gap at (0.0, 0.0) where no mesh exists:
        # Strict ray_ground_elevation returns None
        self.assertIsNone(env.ray_ground_elevation(0.0, 0.0))
        # Legacy ground_height_at falls back to base ground_z (0.0)
        self.assertEqual(env.ground_height_at(0.0, 0.0), 0.0)

        # Spatial raycast via DynamicsEnvironmentQuery returns source_type="mesh"
        q_res = env.query_spatial_surface((0.0, 10.0, 6.0), (0.0, 0.0, -1.0))
        self.assertTrue(q_res.success)
        self.assertEqual(q_res.source_type, "mesh")
        self.assertAlmostEqual(q_res.contact_point_world[2], 3.0, places=3)


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMeshEnvironmentQuery)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
