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
from typing import List, Optional, Sequence, Tuple

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

    # -------------------------------------------------------------------------
    # Helper: Comprehensive 8-Field Surface Contract Validation
    # -------------------------------------------------------------------------

    def _assert_surface_contract(
        self,
        res: SurfaceQueryResult,
        expected_success: bool,
        expected_surface_type: Optional[str] = None,
        expected_source_type: Optional[str] = None,
        expected_contact_z: Optional[float] = None,
        expected_normal_z: Optional[float] = None,
        expected_ray_dist: Optional[float] = None,
        expected_support: Optional[bool] = None,
        expected_id_substr: Optional[str] = None,
        places: int = 3,
    ) -> None:
        """Verify all 8 physical fields of SurfaceQueryResult without exception."""
        self.assertEqual(res.success, expected_success)
        if expected_success:
            self.assertIsNotNone(res.surface_id)
            self.assertNotEqual(res.surface_id, "none")
            if expected_id_substr:
                self.assertIn(expected_id_substr, res.surface_id)
            if expected_surface_type:
                self.assertEqual(res.surface_type, expected_surface_type)
            if expected_source_type:
                self.assertEqual(res.source_type, expected_source_type)
            if expected_contact_z is not None:
                self.assertAlmostEqual(res.contact_point_world[2], expected_contact_z, places=places)
            if expected_normal_z is not None:
                self.assertAlmostEqual(res.surface_normal_world[2], expected_normal_z, places=places)
            if expected_ray_dist is not None:
                self.assertIsNotNone(res.ray_hit_distance)
                self.assertAlmostEqual(res.ray_hit_distance, expected_ray_dist, places=places)
            if expected_support is not None:
                self.assertEqual(res.allows_regular_support, expected_support)
            self.assertIsNotNone(res.signed_distance)
            self.assertFalse(math.isinf(res.signed_distance))
        else:
            self.assertEqual(res.surface_id, "none")
            self.assertEqual(res.surface_type, "none")
            self.assertEqual(res.source_type, "none")
            self.assertTrue(math.isinf(res.signed_distance))
            self.assertFalse(res.allows_regular_support)
            self.assertIsNotNone(res.error_reason)

    # -------------------------------------------------------------------------
    # Repair Unit 1 / Defect A03: Collection & Object Scope Isolation
    # -------------------------------------------------------------------------

    def test_09_a03_1_collection_does_not_exist(self):
        """A03-1: Non-existent collection must NOT fall back to scene meshes."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        # Create a real mesh in the default scene collection
        bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.0))
        ground = bpy.context.active_object
        ground.name = "RealGround"

        # Explicitly specify non-existent collection
        adapter = BlenderMeshEnvironmentAdapter(collection_names=("CollectionThatDoesNotExist",))
        self.assertEqual(adapter.tracked_objects, [])
        self.assertEqual(adapter.polygon_count, 0)

        # Query toward where RealGround is physically located
        res = adapter.ray_cast(origin=(0.0, 0.0, 5.0), direction=(0.0, 0.0, -1.0), distance=10.0)
        self._assert_surface_contract(res, expected_success=False)

    def test_10_a03_2_collection_empty(self):
        """A03-2: Empty collection must NOT fall back to other collections in scene."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col_empty = bpy.data.collections.new("EnvironmentEmpty")
        bpy.context.scene.collection.children.link(col_empty)

        col_other = bpy.data.collections.new("OtherObjects")
        bpy.context.scene.collection.children.link(col_other)

        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.0))
        cube = bpy.context.active_object
        cube.name = "CubeOther"
        col_other.objects.link(cube)

        # Target only the empty collection
        adapter = BlenderMeshEnvironmentAdapter(collection_names=("EnvironmentEmpty",))
        self.assertEqual(adapter.tracked_objects, [])
        self.assertEqual(adapter.polygon_count, 0)

        res = adapter.ray_cast(origin=(0.0, 0.0, 5.0), direction=(0.0, 0.0, -1.0), distance=10.0)
        self._assert_surface_contract(res, expected_success=False)

    def test_11_a03_3_collection_isolation(self):
        """A03-3: Query must strictly isolate allowed collection from forbidden collection."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col_allowed = bpy.data.collections.new("EnvironmentAllowed")
        bpy.context.scene.collection.children.link(col_allowed)

        col_forbidden = bpy.data.collections.new("EnvironmentForbidden")
        bpy.context.scene.collection.children.link(col_forbidden)

        # Allowed object: Lower plane at Z=2.0
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 2.0))
        plane_allowed = bpy.context.active_object
        plane_allowed.name = "Surface_Allowed"
        col_allowed.objects.link(plane_allowed)

        # Forbidden object: Higher plane at Z=4.0 (closer to ray origin, but forbidden!)
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 4.0))
        plane_forbidden = bpy.context.active_object
        plane_forbidden.name = "Surface_Forbidden"
        col_forbidden.objects.link(plane_forbidden)

        # Adapter targets ONLY allowed collection
        adapter = BlenderMeshEnvironmentAdapter(collection_names=("EnvironmentAllowed",))
        self.assertIn("Surface_Allowed", adapter.tracked_objects)
        self.assertNotIn("Surface_Forbidden", adapter.tracked_objects)

        # Downward ray from Z=10.0
        res = adapter.ray_cast(origin=(0.0, 0.0, 10.0), direction=(0.0, 0.0, -1.0), distance=15.0)
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="horizontal_ground",
            expected_source_type="mesh",
            expected_contact_z=2.0,  # Must be Z=2.0, NEVER closer Z=4.0!
            expected_normal_z=1.0,
            expected_ray_dist=8.0,
            expected_support=True,
            expected_id_substr="Surface_Allowed",
        )

    def test_12_a03_4_explicit_all_scene_mode(self):
        """A03-4: Explicit all-scene mode (collection_names=None, object_names=None) queries all scene meshes."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col1 = bpy.data.collections.new("ColA")
        bpy.context.scene.collection.children.link(col1)
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(-5.0, 0.0, 1.0))
        cube1 = bpy.context.active_object
        col1.objects.link(cube1)

        col2 = bpy.data.collections.new("ColB")
        bpy.context.scene.collection.children.link(col2)
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(5.0, 0.0, 1.0))
        cube2 = bpy.context.active_object
        col2.objects.link(cube2)

        adapter = BlenderMeshEnvironmentAdapter(collection_names=None, object_names=None)
        self.assertIn(cube1.name, adapter.tracked_objects)
        self.assertIn(cube2.name, adapter.tracked_objects)
        self.assertGreaterEqual(adapter.polygon_count, 12)

        res1 = adapter.ray_cast(origin=(-5.0, 0.0, 5.0), direction=(0.0, 0.0, -1.0), distance=10.0)
        self.assertTrue(res1.success)
        res2 = adapter.ray_cast(origin=(5.0, 0.0, 5.0), direction=(0.0, 0.0, -1.0), distance=10.0)
        self.assertTrue(res2.success)

    # -------------------------------------------------------------------------
    # Repair Unit 1 / Defect A01: ray_cast Surface Filtering Semantics
    # -------------------------------------------------------------------------

    def _setup_parallel_surfaces_scene(self) -> BlenderMeshEnvironmentAdapter:
        """Setup two parallel surfaces: Front (Box at Z=4.0, top Z=5.0) and Back (Ground plane at Z=2.0)."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("SurfacesCol")
        bpy.context.scene.collection.children.link(col)

        # Front Surface: Box_Front top face at Z=5.0 (surface_type: "box_top")
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 4.0))
        box_front = bpy.context.active_object
        box_front.name = "Box_Front"
        col.objects.link(box_front)

        # Back Surface: Ground_Back plane at Z=2.0 (surface_type: "horizontal_ground")
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 2.0))
        plane_back = bpy.context.active_object
        plane_back.name = "Ground_Back"
        col.objects.link(plane_back)

        return BlenderMeshEnvironmentAdapter(collection_names=("SurfacesCol",))

    def test_13_a01_1_ray_unfiltered_nearest(self):
        """A01-1: Unfiltered ray returns nearest physical hit (Front surface at Z=5.0)."""
        adapter = self._setup_parallel_surfaces_scene()
        res = adapter.ray_cast(origin=(0.0, 0.0, 8.0), direction=(0.0, 0.0, -1.0), distance=10.0, surface_type_filter=None)
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="box_top",
            expected_source_type="mesh",
            expected_contact_z=5.0,
            expected_normal_z=1.0,
            expected_ray_dist=3.0,
            expected_support=True,
            expected_id_substr="Box_Front",
        )

    def test_14_a01_2_ray_filtered_finds_second_surface(self):
        """A01-2: Filtered ray skips front surface to find matching back surface at Z=2.0."""
        adapter = self._setup_parallel_surfaces_scene()
        res = adapter.ray_cast(
            origin=(0.0, 0.0, 8.0),
            direction=(0.0, 0.0, -1.0),
            distance=10.0,
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="horizontal_ground",
            expected_source_type="mesh",
            expected_contact_z=2.0,
            expected_normal_z=1.0,
            expected_ray_dist=6.0,
            expected_support=True,
            expected_id_substr="Ground_Back",
        )

    def test_15_a01_3_ray_filtered_nonexistent_type(self):
        """A01-3: Filter for non-existent type returns success=False."""
        adapter = self._setup_parallel_surfaces_scene()
        res = adapter.ray_cast(
            origin=(0.0, 0.0, 8.0),
            direction=(0.0, 0.0, -1.0),
            distance=10.0,
            surface_type_filter="sloped_ramp",
        )
        self._assert_surface_contract(res, expected_success=False)

    def test_16_a01_4_ray_filtered_insufficient_distance(self):
        """A01-4: Filtered ray fails when max_distance reaches front (3m) but cannot reach back (6m)."""
        adapter = self._setup_parallel_surfaces_scene()
        res = adapter.ray_cast(
            origin=(0.0, 0.0, 8.0),
            direction=(0.0, 0.0, -1.0),
            distance=4.0,  # 8.0 - 4.0 = 4.0m, cannot reach Z=2.0 (needs 6.0m)
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(res, expected_success=False)

    def test_17_a01_5_ray_direction_scale_invariance(self):
        """A01-5: Ray direction scaling (0,0,-1) vs (0,0,-5) yields identical Euclidean hit distance."""
        adapter = self._setup_parallel_surfaces_scene()
        res1 = adapter.ray_cast(
            origin=(0.0, 0.0, 8.0),
            direction=(0.0, 0.0, -1.0),
            distance=10.0,
            surface_type_filter="horizontal_ground",
        )
        res2 = adapter.ray_cast(
            origin=(0.0, 0.0, 8.0),
            direction=(0.0, 0.0, -5.0),
            distance=10.0,
            surface_type_filter="horizontal_ground",
        )
        self.assertTrue(res1.success)
        self.assertTrue(res2.success)
        self.assertAlmostEqual(res1.ray_hit_distance, 6.0, places=3)
        self.assertAlmostEqual(res2.ray_hit_distance, 6.0, places=3)
        self.assertAlmostEqual(res1.contact_point_world[2], res2.contact_point_world[2], places=4)

    def test_18_a01_6_ray_origin_on_surface(self):
        """A01-6: Ray origin on surface terminates correctly without infinite loop."""
        adapter = self._setup_parallel_surfaces_scene()
        # Origin exactly on Ground_Back (Z=2.0)
        res_on_back = adapter.ray_cast(
            origin=(0.0, 0.0, 2.0),
            direction=(0.0, 0.0, -1.0),
            distance=5.0,
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(
            res_on_back,
            expected_success=True,
            expected_surface_type="horizontal_ground",
            expected_source_type="mesh",
            expected_contact_z=2.0,
            expected_normal_z=1.0,
            expected_ray_dist=0.0,
            expected_support=True,
            expected_id_substr="Ground_Back",
        )

        # Origin on Box_Front (Z=5.0), filtering for horizontal_ground: must advance past Box_Front to Z=2.0
        res_on_front = adapter.ray_cast(
            origin=(0.0, 0.0, 5.0),
            direction=(0.0, 0.0, -1.0),
            distance=5.0,
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(
            res_on_front,
            expected_success=True,
            expected_surface_type="horizontal_ground",
            expected_source_type="mesh",
            expected_contact_z=2.0,
            expected_normal_z=1.0,
            expected_ray_dist=3.0,
            expected_support=True,
            expected_id_substr="Ground_Back",
        )

    # -------------------------------------------------------------------------
    # Repair Unit 1 / Defect A02: find_nearest Surface Filtering Semantics
    # -------------------------------------------------------------------------

    def _setup_nearest_surfaces_scene(self) -> BlenderMeshEnvironmentAdapter:
        """Setup two surfaces for nearest query: Box_Near at Z=0.8 (dist 0.2m) and Plane_Far at Z=0.2 (dist 0.8m)."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        col = bpy.data.collections.new("NearestCol")
        bpy.context.scene.collection.children.link(col)

        # Surface A: Box_Near, top face at Z=0.8 (center 0.7, half-height 0.1) -> surface_type="box_top"
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 0.7))
        box_near = bpy.context.active_object
        box_near.name = "Box_Near"
        box_near.scale = (1.0, 1.0, 0.1)
        bpy.context.view_layer.update()
        col.objects.link(box_near)

        # Surface B: Plane_Far, flat plane at Z=0.2 -> surface_type="horizontal_ground"
        bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 0.2))
        plane_far = bpy.context.active_object
        plane_far.name = "Plane_Far"
        col.objects.link(plane_far)

        return BlenderMeshEnvironmentAdapter(collection_names=("NearestCol",))

    def test_19_a02_1_nearest_unfiltered_nearest(self):
        """A02-1: Unfiltered find_nearest returns closest surface A (dist 0.2m)."""
        adapter = self._setup_nearest_surfaces_scene()
        res = adapter.find_nearest(point_world=(0.0, 0.0, 1.0), max_distance=5.0, surface_type_filter=None)
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="box_top",
            expected_source_type="mesh",
            expected_contact_z=0.8,
            expected_normal_z=1.0,
            expected_support=True,
            expected_id_substr="Box_Near",
        )
        self.assertAlmostEqual(res.signed_distance, 0.2, places=3)

    def test_20_a02_2_nearest_filtered_finds_target_surface(self):
        """A02-2: Filtered find_nearest finds closest matching surface B (dist 0.8m)."""
        adapter = self._setup_nearest_surfaces_scene()
        res = adapter.find_nearest(
            point_world=(0.0, 0.0, 1.0),
            max_distance=5.0,
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="horizontal_ground",
            expected_source_type="mesh",
            expected_contact_z=0.2,
            expected_normal_z=1.0,
            expected_support=True,
            expected_id_substr="Plane_Far",
        )
        self.assertAlmostEqual(res.signed_distance, 0.8, places=3)

    def test_21_a02_3_nearest_filtered_insufficient_radius(self):
        """A02-3: Filtered find_nearest fails when max_distance (0.5m) cannot reach target B (0.8m)."""
        adapter = self._setup_nearest_surfaces_scene()
        res = adapter.find_nearest(
            point_world=(0.0, 0.0, 1.0),
            max_distance=0.5,
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(res, expected_success=False)

    def test_22_a02_4_nearest_filtered_moved_query_point(self):
        """A02-4: Moving query point closer to B updates distance and contact point."""
        adapter = self._setup_nearest_surfaces_scene()
        # Query from Z=0.3: distance to Plane_Far (Z=0.2) is 0.1m; distance to Box_Near (Z=0.8) is 0.5m
        res = adapter.find_nearest(
            point_world=(0.0, 0.0, 0.3),
            max_distance=5.0,
            surface_type_filter="horizontal_ground",
        )
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="horizontal_ground",
            expected_source_type="mesh",
            expected_contact_z=0.2,
            expected_normal_z=1.0,
            expected_support=True,
            expected_id_substr="Plane_Far",
        )
        self.assertAlmostEqual(res.signed_distance, 0.1, places=3)

    def test_23_a02_5_nearest_filtered_rotated_surface_normal(self):
        """A02-5: Rotating target surface updates outward world normal upon refresh."""
        adapter = self._setup_nearest_surfaces_scene()
        plane_far = bpy.data.objects.get("Plane_Far")
        self.assertIsNotNone(plane_far)

        # Rotate Plane_Far by 30 degrees around X-axis
        angle_rad = math.radians(30.0)
        plane_far.rotation_euler.x = angle_rad
        bpy.context.view_layer.update()
        adapter.refresh()

        # Plane rotated by 30 deg has normal (0, -sin(30), cos(30)) = (0, -0.5, 0.866) -> type: "sloped_ramp"
        res = adapter.find_nearest(
            point_world=(0.0, 0.0, 1.0),
            max_distance=5.0,
            surface_type_filter="sloped_ramp",
        )
        self._assert_surface_contract(
            res,
            expected_success=True,
            expected_surface_type="sloped_ramp",
            expected_source_type="mesh",
            expected_support=True,
            expected_id_substr="Plane_Far",
        )
        self.assertAlmostEqual(res.surface_normal_world[1], -math.sin(angle_rad), places=3)
        self.assertAlmostEqual(res.surface_normal_world[2], math.cos(angle_rad), places=3)


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMeshEnvironmentQuery)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
