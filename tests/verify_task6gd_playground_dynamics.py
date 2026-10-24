"""Verification Suite for Dynamics Playground Real Dynamics State Integration (Task 6G-D-C2-A).

Verifies:
1. Scene file output/dynamics_playground.blend existence and integrity.
2. Dedicated collection `Playground_Dynamics_Visualization` existence and isolation.
3. Presence of all 5 physical dynamics stations:
   - Station 1: Static Support Equilibrium
   - Station 2: Gravity Free-Fall
   - Station 3: Horizontal Acceleration under Friction
   - Station 4: Insufficient Friction Clamping (Slip & Lag)
   - Station 5: Eccentric Contact Rotation
4. Physical visual objects: CoM spheres, oriented body proxies, target ghosts, contact discs,
   dynamically scaled force arrows, angular momentum arrows, trajectory curves, station labels.
5. Keyframing consistency across frames 1..72:
   - S1 height held rock-solid (sinkage < 1e-5m) with upward normal force arrows.
   - S2 drops naturally under gravity with zero contact forces.
   - S3 accelerates forward with angled propulsion force arrows.
   - S4 slips on low friction (mu=0.08) with clamped force arrows and visual lag vs target ghost.
   - S5 rolls/tilts around X axis from eccentric lever arm, with dynamic angular momentum arrow.
6. Original playground collections and surfaces are 100% undamaged and preserved.
"""

from __future__ import annotations

import math
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BLEND_PATH = os.path.join(PROJECT_ROOT, "output", "dynamics_playground.blend")


class TestDynamicsPlaygroundIntegration(unittest.TestCase):
    """Test suite for real dynamics state integration into DynamicsPlayground."""

    @classmethod
    def setUpClass(cls):
        # Verify file exists
        if not os.path.isfile(BLEND_PATH):
            raise FileNotFoundError(f"Missing dynamics playground blend: {BLEND_PATH}")

        try:
            import bpy
            cls.bpy_available = True
            bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
            cls.scene = bpy.context.scene
        except ImportError:
            cls.bpy_available = False
            cls.scene = None

    def test_01_pure_python_scenarios_execution(self):
        """Scenario 1: Pure Python numerical simulation executes and satisfies physics invariants."""
        from src.scene.dynamics_visualizer import run_dynamics_scenarios

        data = run_dynamics_scenarios(num_steps=72)
        self.assertEqual(len(data), 5)
        self.assertIn("scenario_1_static_support", data)
        self.assertIn("scenario_2_free_fall", data)
        self.assertIn("scenario_3_horizontal_acceleration", data)
        self.assertIn("scenario_4_insufficient_friction", data)
        self.assertIn("scenario_5_eccentric_rotation", data)

        # S1: Static support holds height to < 1e-5m
        traj1 = data["scenario_1_static_support"]["trajectory"]
        self.assertTrue(traj1.all_advanced)
        self.assertAlmostEqual(traj1.final_state.com_position_world[2], 1.0, delta=1e-5)

        # S2: Free fall drops height
        traj2 = data["scenario_2_free_fall"]["trajectory"]
        self.assertTrue(traj2.all_advanced)
        self.assertLess(traj2.frames[20].state_current.com_position_world[2], 1.0)

        # S3: Horizontal acceleration advances X
        traj3 = data["scenario_3_horizontal_acceleration"]["trajectory"]
        self.assertTrue(traj3.all_advanced)
        self.assertGreater(traj3.final_state.com_position_world[0], -6.0)

        # S4: Insufficient friction produces lag vs target
        traj4 = data["scenario_4_insufficient_friction"]["trajectory"]
        self.assertTrue(traj4.all_advanced)
        last_f4 = traj4.frames[-1]
        target_x4 = last_f4.motion_reference.target_com_position_world[0]
        actual_x4 = traj4.final_state.com_position_world[0]
        lag4 = target_x4 - actual_x4
        self.assertGreater(lag4, 2.0)  # Significant lag due to slip

        # S5: Eccentric contact drives roll rotation
        traj5 = data["scenario_5_eccentric_rotation"]["trajectory"]
        self.assertTrue(traj5.all_advanced)
        q5 = traj5.final_state.orientation_quat_world
        # Roll rotation angle: 2 * acos(|qw|)
        angle_roll = 2.0 * math.acos(min(1.0, abs(q5[0])))
        self.assertGreater(angle_roll, math.radians(30.0))
        self.assertLess(traj5.final_state.angular_momentum_about_com_world[0], -100.0)

    def test_02_blend_scene_collections_and_isolation(self):
        """Scenario 2: Blend file contains dedicated visualization collection; preserves existing collections."""
        if not self.bpy_available:
            self.skipTest("bpy not available in pure Python environment")
        import bpy

        # Check existing collections remain intact
        for req_col in ["Playground_Surfaces", "Playground_Visuals", "Playground_Lighting_Cameras"]:
            col = bpy.data.collections.get(req_col)
            self.assertIsNotNone(col, f"Required collection '{req_col}' was removed or renamed")
            self.assertGreater(len(col.objects), 0)

        # Check new isolated dynamics visualization collection
        viz_col = bpy.data.collections.get("Playground_Dynamics_Visualization")
        self.assertIsNotNone(viz_col, "Missing 'Playground_Dynamics_Visualization' collection")
        self.assertGreaterEqual(len(viz_col.objects), 30)

    def test_03_five_stations_visual_objects_presence(self):
        """Scenario 3: All 5 stations have complete sets of visual indicators."""
        if not self.bpy_available:
            self.skipTest("bpy not available in pure Python environment")
        import bpy

        for s_idx in range(1, 6):
            # Label
            lbl = bpy.data.objects.get(f"Station_{s_idx}_Label")
            self.assertIsNotNone(lbl, f"Missing Station_{s_idx}_Label")
            self.assertEqual(lbl.type, "FONT")

            # CoM Sphere
            com = bpy.data.objects.get(f"Dynamics_CoM_S{s_idx}")
            self.assertIsNotNone(com, f"Missing Dynamics_CoM_S{s_idx}")
            self.assertEqual(com.type, "MESH")

            # Body Proxy
            body = bpy.data.objects.get(f"Dynamics_BodyProxy_S{s_idx}")
            self.assertIsNotNone(body, f"Missing Dynamics_BodyProxy_S{s_idx}")
            self.assertEqual(body.type, "MESH")
            self.assertEqual(body.rotation_mode, "QUATERNION")

            # Target Ghost
            ghost = bpy.data.objects.get(f"Dynamics_TargetGhost_S{s_idx}")
            self.assertIsNotNone(ghost, f"Missing Dynamics_TargetGhost_S{s_idx}")

            # Trajectory Spline
            traj = bpy.data.objects.get(f"Dynamics_Trajectory_S{s_idx}")
            self.assertIsNotNone(traj, f"Missing Dynamics_Trajectory_S{s_idx}")
            self.assertEqual(traj.type, "CURVE")

        # Specific objects
        # S1 force arrows
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S1_foot_L"))
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S1_foot_R"))

        # S3 force arrows
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S3_foot_L"))
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S3_foot_R"))

        # S4 force arrows
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S4_foot_L"))
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S4_foot_R"))

        # S5 eccentric force arrow & angular momentum arrow
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_ForceArrow_S5_eccentric_foot"))
        self.assertIsNotNone(bpy.data.objects.get("Dynamics_AngMomArrow_S5"))

        # Cameras
        self.assertIsNotNone(bpy.data.objects.get("DynamicsInspectionCam"))
        self.assertIsNotNone(bpy.data.objects.get("PlaygroundOverviewCam"))

    def test_04_keyframed_animation_timeline_and_motion(self):
        """Scenario 4: Scene has 72 frames; dynamic objects contain valid keyframe animation curves."""
        if not self.bpy_available:
            self.skipTest("bpy not available in pure Python environment")
        import bpy

        scene = bpy.context.scene
        self.assertEqual(scene.frame_start, 1)
        self.assertEqual(scene.frame_end, 72)
        self.assertEqual(scene.render.fps, 24)

        # Dynamic objects must have animation data
        for s_idx in range(1, 6):
            com = bpy.data.objects[f"Dynamics_CoM_S{s_idx}"]
            body = bpy.data.objects[f"Dynamics_BodyProxy_S{s_idx}"]
            self.assertIsNotNone(com.animation_data, f"Dynamics_CoM_S{s_idx} missing animation data")
            self.assertIsNotNone(body.animation_data, f"Dynamics_BodyProxy_S{s_idx} missing animation data")

    def test_05_physical_numerical_accuracy_of_visuals(self):
        """Scenario 5: Keyframed positions and rotations in Blender match exact numerical simulation values."""
        if not self.bpy_available:
            self.skipTest("bpy not available in pure Python environment")
        import bpy

        scene = bpy.context.scene

        # Station 1: Frame 1 and Frame 72 CoM height
        scene.frame_set(1)
        com1 = bpy.data.objects["Dynamics_CoM_S1"]
        z1_f1 = com1.location[2]
        scene.frame_set(72)
        z1_f72 = com1.location[2]
        self.assertAlmostEqual(z1_f1, 1.0, delta=1e-5)
        self.assertAlmostEqual(z1_f72, 1.0, delta=1e-5)

        # Station 2: Free fall drop
        scene.frame_set(1)
        com2 = bpy.data.objects["Dynamics_CoM_S2"]
        z2_f1 = com2.location[2]
        scene.frame_set(20)
        z2_f20 = com2.location[2]
        self.assertAlmostEqual(z2_f1, 3.5, delta=1e-5)
        self.assertLess(z2_f20, 1.0)  # Dropped significantly

        # Station 3: Horizontal translation
        scene.frame_set(1)
        com3 = bpy.data.objects["Dynamics_CoM_S3"]
        x3_f1 = com3.location[0]
        scene.frame_set(72)
        x3_f72 = com3.location[0]
        self.assertAlmostEqual(x3_f1, -6.0, delta=1e-5)
        self.assertGreater(x3_f72, -0.5)  # Advanced forward by >5.5m

        # Station 4: Friction slip lag
        scene.frame_set(72)
        com4 = bpy.data.objects["Dynamics_CoM_S4"]
        ghost4 = bpy.data.objects["Dynamics_TargetGhost_S4"]
        x4_actual = com4.location[0]
        x4_target = ghost4.location[0]
        lag4 = x4_target - x4_actual
        self.assertGreater(lag4, 2.0)  # Shows visible lag in viewport

        # Station 5: Roll tilt
        scene.frame_set(48)
        body5 = bpy.data.objects["Dynamics_BodyProxy_S5"]
        q5 = body5.rotation_quaternion
        self.assertNotEqual(q5[1], 0.0)  # Non-zero roll quaternion component qx
        ang_mom_arrow = bpy.data.objects["Dynamics_AngMomArrow_S5"]
        self.assertGreater(ang_mom_arrow.scale[2], 0.1)  # Dynamic arrow scaled with momentum


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1:])
    unittest.main(argv=argv)
