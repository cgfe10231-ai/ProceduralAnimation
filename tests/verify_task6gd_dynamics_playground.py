"""Comprehensive Mathematical and Geometric Verification of Dynamics Environment Query (Task 6G-D-PRE-P2).

Verifies the 10 core requirements:
1. Flat ground height and normal vector.
2. Sloped ramp normal direction, inclination angle, and exact unit length.
3. Stair tread and riser geometric dimensions and elevation progression.
4. Vertical wall normal direction, spatial query, and non-support classification.
5. Contact point projection accuracy across all surfaces (sub-millimeter).
6. Signed distance convention (gap > 0, penetration < 0).
7. In-bounds vs out-of-bounds footprint and Euclidean distance handling.
8. Inter-surface boundary and transition continuity.
9. Translation and rotation consistency of OrientedSurface queries.
10. Absence of NaN / Inf or degenerate geometry parameters.
11. 100% backward compatibility with EnvironmentQuery.

Runs fast in pure Python without heavy scene dependencies.
"""

import math
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    EnvironmentQuery,
    OrientedSurface,
    SurfaceGeometryType,
    SurfaceQueryResult,
    create_standard_dynamics_playground_query,
)


class TestDynamicsEnvironmentQuery(unittest.TestCase):
    """Unit test suite verifying mathematical correctness of DynamicsEnvironmentQuery."""

    @classmethod
    def setUpClass(cls):
        cls.query = create_standard_dynamics_playground_query()

    def test_01_flat_ground_height_and_normal(self):
        """Req 1: Horizontal flat ground must return exact Z=0.0m and normal=(0, 0, 1)."""
        # Inside Zone 1 flat ground (X in [-10, 10], Y in [-10, 5])
        test_points = [
            (0.0, 0.0),
            (2.5, -4.0),
            (-8.0, 2.0),
            (7.0, -8.0),
        ]
        for x, y in test_points:
            z = self.query.ground_height_at(x, y)
            normal = self.query.surface_normal_at(x, y)
            self.assertAlmostEqual(z, 0.0, places=5, msg=f"Ground height failed at ({x}, {y})")
            self.assertAlmostEqual(normal[0], 0.0, places=5)
            self.assertAlmostEqual(normal[1], 0.0, places=5)
            self.assertAlmostEqual(normal[2], 1.0, places=5)

    def test_02_sloped_ramp_normals_and_unit_lengths(self):
        """Req 2: Sloped ramps must have exact unit normals pointing outward into free space."""
        ramp_up = self.query.get_surface_by_id("ramp_up")
        self.assertIsNotNone(ramp_up)

        # 15 degree uphill ramp
        nx, ny, nz = ramp_up.normal
        norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        self.assertAlmostEqual(norm_len, 1.0, places=6, msg="Ramp up normal not unit length")
        self.assertAlmostEqual(nx, 0.0, places=5)
        # For +15 deg uphill in +Y, outward normal tilts backwards (-Y)
        expected_ny = -math.sin(math.radians(15.0))
        expected_nz = math.cos(math.radians(15.0))
        self.assertAlmostEqual(ny, expected_ny, places=5)
        self.assertAlmostEqual(nz, expected_nz, places=5)

        # Ramp down (20 degree downhill)
        ramp_down = self.query.get_surface_by_id("ramp_down")
        self.assertIsNotNone(ramp_down)
        dx, dy, dz = ramp_down.normal
        d_norm_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        self.assertAlmostEqual(d_norm_len, 1.0, places=6, msg="Ramp down normal not unit length")
        expected_dy = math.sin(math.radians(20.0))
        expected_dz = math.cos(math.radians(20.0))
        self.assertAlmostEqual(dy, expected_dy, places=5)
        self.assertAlmostEqual(dz, expected_dz, places=5)

        # Query height and normal at ramp up midpoint (Y = 13.5m)
        mid_y = 13.5
        expected_mid_z = (mid_y - 11.0) * math.tan(math.radians(15.0))
        actual_z = self.query.ground_height_at(0.0, mid_y)
        actual_norm = self.query.surface_normal_at(0.0, mid_y)
        self.assertAlmostEqual(actual_z, expected_mid_z, places=4)
        self.assertAlmostEqual(actual_norm[1], expected_ny, places=4)
        self.assertAlmostEqual(actual_norm[2], expected_nz, places=4)

    def test_03_stair_tread_and_riser_geometry(self):
        """Req 3: Stairs must have 5 steps each of depth 0.3m and rise 0.15m."""
        stair_start_y = 6.0
        tread_depth = 0.30
        riser_height = 0.15

        for i in range(5):
            idx = i + 1
            tread_id = f"stair_tread_{idx:02d}"
            riser_id = f"stair_riser_{idx:02d}"

            tread = self.query.get_surface_by_id(tread_id)
            riser = self.query.get_surface_by_id(riser_id)
            self.assertIsNotNone(tread, f"Missing {tread_id}")
            self.assertIsNotNone(riser, f"Missing {riser_id}")

            # Check tread elevation
            expected_z = idx * riser_height
            self.assertAlmostEqual(tread.center[2], expected_z, places=5)
            self.assertEqual(tread.normal, (0.0, 0.0, 1.0))
            self.assertTrue(tread.allows_regular_support)

            # Check riser vertical wall
            self.assertEqual(riser.normal, (0.0, -1.0, 0.0))
            self.assertFalse(riser.allows_regular_support)

            # Query elevation directly in middle of step
            test_y = stair_start_y + i * tread_depth + tread_depth / 2.0
            actual_step_z = self.query.ground_height_at(0.0, test_y)
            self.assertAlmostEqual(actual_step_z, expected_z, places=4)

        # Check top landing platform (Z = 0.75m)
        plat = self.query.get_surface_by_id("stair_top_platform")
        self.assertIsNotNone(plat)
        self.assertAlmostEqual(plat.center[2], 0.75, places=5)
        plat_z = self.query.ground_height_at(0.0, 8.5)
        self.assertAlmostEqual(plat_z, 0.75, places=4)

    def test_04_vertical_wall_spatial_query_and_non_support(self):
        """Req 4: Vertical wall normal (0, -1, 0), spatial query, and non-support classification."""
        wall = self.query.get_surface_by_id("vertical_wall_front")
        self.assertIsNotNone(wall)
        self.assertEqual(wall.normal, (0.0, -1.0, 0.0))
        self.assertFalse(wall.allows_regular_support)
        self.assertEqual(wall.surface_type, SurfaceGeometryType.VERTICAL_WALL)

        # 3D Point query in front of wall (X=0.0, Y=23.5, Z=1.5m)
        # Wall is at Y = 23.8m. Gap distance should be exactly 23.8 - 23.5 = 0.3m.
        res = self.query.query_surface_at_point((0.0, 23.5, 1.5))
        self.assertTrue(res.success)
        self.assertEqual(res.surface_id, "vertical_wall_front")
        self.assertEqual(res.surface_normal_world, (0.0, -1.0, 0.0))
        self.assertAlmostEqual(res.signed_distance, 0.30, places=4)
        self.assertAlmostEqual(res.contact_point_world[0], 0.0, places=4)
        self.assertAlmostEqual(res.contact_point_world[1], 23.8, places=4)
        self.assertAlmostEqual(res.contact_point_world[2], 1.5, places=4)
        self.assertFalse(res.allows_regular_support)

    def test_05_contact_point_projection_precision(self):
        """Req 5: Projected contact point must lie strictly on the analytical surface patch."""
        # Query box platform top (Z = 0.90m, Y in [26.5, 29.5], X in [-2.5, 2.5])
        query_pt = (1.2, 28.0, 1.4)  # 0.5m above box top
        res = self.query.query_surface_at_point(query_pt)
        self.assertTrue(res.success)
        self.assertEqual(res.surface_id, "vault_box_top")
        self.assertAlmostEqual(res.contact_point_world[0], 1.2, places=5)
        self.assertAlmostEqual(res.contact_point_world[1], 28.0, places=5)
        self.assertAlmostEqual(res.contact_point_world[2], 0.90, places=5)
        self.assertAlmostEqual(res.signed_distance, 0.50, places=5)

    def test_06_signed_distance_convention(self):
        """Req 6: Signed distance must be positive for gap (outside) and negative for penetration (inside)."""
        # Horizontal ground at Z=0.0
        outside_pt = (0.0, 0.0, 0.25)   # 25cm above ground
        on_surface_pt = (0.0, 0.0, 0.0) # on ground
        inside_pt = (0.0, 0.0, -0.15)   # 15cm underground

        res_out = self.query.query_surface_at_point(outside_pt)
        self.assertGreater(res_out.signed_distance, 0.0)
        self.assertAlmostEqual(res_out.signed_distance, 0.25, places=5)

        res_on = self.query.query_surface_at_point(on_surface_pt)
        self.assertAlmostEqual(res_on.signed_distance, 0.0, places=5)

        res_in = self.query.query_surface_at_point(inside_pt)
        self.assertLess(res_in.signed_distance, 0.0)
        self.assertAlmostEqual(res_in.signed_distance, -0.15, places=5)

        # Vertical wall front at Y=23.8 (facing -Y)
        # Point in front (Y=23.6): Gap > 0
        res_wall_out = self.query.query_surface_at_point((0.0, 23.6, 1.0))
        self.assertAlmostEqual(res_wall_out.signed_distance, 0.20, places=5)

        # Point inside wall (Y=23.9): Penetration < 0
        res_wall_in = self.query.query_surface_at_point((0.0, 23.9, 1.0))
        self.assertAlmostEqual(res_wall_in.signed_distance, -0.10, places=5)

    def test_07_surface_boundary_inside_and_outside(self):
        """Req 7: Points outside rectangular perimeter must clamp to edge and report Euclidean distance."""
        # Box top is X in [-2.5, 2.5], Y in [26.5, 29.5], Z = 0.90m
        box = self.query.get_surface_by_id("vault_box_top")
        self.assertIsNotNone(box)

        # Point directly above center
        proj_in, dist_in, _ = box.query_closest_point(0.0, 28.0, 1.90)
        self.assertAlmostEqual(dist_in, 1.0, places=5)
        self.assertAlmostEqual(proj_in[0], 0.0, places=5)

        # Point outside right edge: X = 3.5 (1.0m past X=2.5 edge), Y = 28.0, Z = 0.90m
        proj_out, dist_out, _ = box.query_closest_point(3.5, 28.0, 0.90)
        self.assertAlmostEqual(proj_out[0], 2.5, places=5)
        self.assertAlmostEqual(proj_out[1], 28.0, places=5)
        self.assertAlmostEqual(proj_out[2], 0.90, places=5)
        self.assertAlmostEqual(dist_out, 1.0, places=5)

    def test_08_inter_surface_boundary_continuity(self):
        """Req 8: Elevations across contiguous zones must match expected transition heights."""
        # Step 5 tread (Y = 7.35m) to Top Platform (Y = 7.60m)
        z_step5 = self.query.ground_height_at(0.0, 7.35)
        z_plat = self.query.ground_height_at(0.0, 7.60)
        self.assertAlmostEqual(z_step5, 0.75, places=4)
        self.assertAlmostEqual(z_plat, 0.75, places=4)

        # Ramp up top (Y = 16.0m) to Ramp bridge (Y = 16.5m)
        ramp_top_z = 5.0 * math.tan(math.radians(15.0))
        z_bridge = self.query.ground_height_at(0.0, 16.5)
        self.assertAlmostEqual(z_bridge, ramp_top_z, places=4)

    def test_09_translation_and_rotation_invariance(self):
        """Req 9: Arbitrary OrientedSurface rotation/translation must maintain exact metric distance."""
        # Create an arbitrarily tilted and rotated surface
        # Center at (10, 20, 5), normal pointing along (1, 1, 1) normalized
        nx, ny, nz = 1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0), 1.0 / math.sqrt(3.0)
        ux, uy, uz = 1.0 / math.sqrt(2.0), -1.0 / math.sqrt(2.0), 0.0
        # v = n x u
        vx = ny * uz - nz * uy  # 1/sqrt(6)
        vy = nz * ux - nx * uz  # 1/sqrt(6)
        vz = nx * uy - ny * ux  # -2/sqrt(6)

        test_patch = OrientedSurface(
            surface_id="arbitrary_patch",
            surface_type=SurfaceGeometryType.SLOPED_RAMP,
            center=(10.0, 20.0, 5.0),
            normal=(nx, ny, nz),
            u_axis=(ux, uy, uz),
            v_axis=(vx, vy, vz),
            half_extents=(2.0, 2.0),
            friction_coeff=0.60,
        )

        # Point offset by 1.5m along normal: p = center + 1.5 * normal
        test_pt = (
            10.0 + 1.5 * nx,
            20.0 + 1.5 * ny,
            5.0 + 1.5 * nz,
        )
        proj, s_dist, norm = test_patch.query_closest_point(*test_pt)
        self.assertAlmostEqual(s_dist, 1.50, places=5)
        self.assertAlmostEqual(proj[0], 10.0, places=5)
        self.assertAlmostEqual(proj[1], 20.0, places=5)
        self.assertAlmostEqual(proj[2], 5.0, places=5)

    def test_10_no_nan_or_inf_in_playground_definitions(self):
        """Req 10: Exhaustive scan of all registered surfaces for zero NaN/Inf or degenerate vectors."""
        all_surfaces = self.query.get_all_surfaces()
        self.assertGreaterEqual(len(all_surfaces), 15, "Playground must have at least 15 analytical surface patches")

        for s in all_surfaces:
            for val in s.center:
                self.assertFalse(math.isnan(val) or math.isinf(val), f"NaN/Inf in {s.surface_id} center")
            for val in s.normal:
                self.assertFalse(math.isnan(val) or math.isinf(val), f"NaN/Inf in {s.surface_id} normal")
            for val in s.half_extents:
                self.assertGreater(val, 0.0, f"Non-positive half extent in {s.surface_id}")
            self.assertGreater(s.friction_coeff, 0.0)

            # Check normal unit length
            nx, ny, nz = s.normal
            self.assertAlmostEqual(math.sqrt(nx * nx + ny * ny + nz * nz), 1.0, places=6)

    def test_11_backward_compatibility_with_environment_query(self):
        """Req 11: Base EnvironmentQuery and DynamicsEnvironmentQuery must be interchangeable."""
        # 1. Base EnvironmentQuery
        base_env = EnvironmentQuery(ground_z=0.0)
        self.assertEqual(base_env.ground_height_at(12.3, 45.6), 0.0)
        self.assertEqual(base_env.surface_normal_at(12.3, 45.6), (0.0, 0.0, 1.0))
        res_base = base_env.query_surface_at_point((1.0, 2.0, 0.5))
        self.assertTrue(res_base.success)
        self.assertAlmostEqual(res_base.signed_distance, 0.5)

        # 2. DynamicsEnvironmentQuery is an instance of EnvironmentQuery
        self.assertIsInstance(self.query, EnvironmentQuery)
        # Default flat ground area behaves identically
        self.assertEqual(self.query.ground_height_at(0.0, 0.0), 0.0)
        self.assertEqual(self.query.surface_normal_at(0.0, 0.0), (0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
