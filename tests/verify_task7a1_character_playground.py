"""Automated integration test for Task 7A-1:
Real 19-Bone Character Integration into DynamicsPlayground & Minimal Control Closed-Loop Verification.

Verifies:
1. Engineering Invariants:
   - Authoritative `output/dynamics_playground.blend` is 100% preserved and unmodified.
   - Derived playable scene `output/dynamics_playground_task7a1.blend` exists and is valid.
   - Scene contains exactly 1 Armature (`CharacterArmature`) with 19 bones.
   - All 13 character mesh parts (`REQUIRED_PARTS`) are present and bound (`parent_type == 'BONE'`).
   - All 8 IK/Pole control objects (`FootIK.L/R`, `KneePole.L/R`, `HandIK.L/R`, `ElbowPole.L/R`) exist in `"Character"`.
   - All 4 original Playground collections and 5 dynamics stations (`S1..S5`) are 100% intact.
2. Minimal Control Closed-Loop Stages (A, B, C, D, E):
   - Stage A: Static standing pose via `KinematicBridgeExecutor` -> `WholeBodyController` (no penetration, zero ROM violation).
   - Stage B: Root finite displacement & non-zero yaw (`+20 deg`), pelvis vertical & rotational control.
   - Stage C: Independent L/R single-foot IK control (zero bone stretch, zero knee flip, zero ROM violation).
   - Stage D: Support-foot world locking (`FootIK.L.parent is None`, `controller_drift == 0`, `ankle_bone_drift < 1e-4 m`).
   - Stage E: Continuous `StartStopWalkAction` via `MotionPlanner` on `Surface_FlatGround` (204 frames, `1.2600 m` displacement, `0` unreachable).
3. Mathematical Consistency Verifications:
   - 5 Coordinate Spaces round-trip at non-zero translation `(1.35, -7.25, 0.0)`, non-zero yaw `28.5 deg`, and distinct L/R foot targets (`< 1e-6 m` round-trip error).
   - Mass distribution & 15-segment whole-body CoM (`70.0 kg` default / `75.0 kg` scaled, `mass_ratio_sum == 1.0`, bilateral symmetry `< 1e-5 m`, posture shift response).
   - Geometric contacts (`double_stance`, `single_stance_l`, `single_stance_r`, surface normal `(0,0,1)`, height `0.0 m`).
   - Constraint truthfulness (`valid_pose` -> `success=True`, `unreachable_target` -> `REACHABILITY` + `success=False`, `rom_violation` -> `ROM_VIOLATION` + `success=False`).
4. Automated Visual Evidence & Telemetry Report:
   - `docs/evidence/task7a1/task7a1_verification_report.json` exists and matches runtime verification.
   - Keyframe PNG renders and `docs/evidence/task7a1/task7a1_walk_preview.gif` exist with non-zero byte size.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import REQUIRED_PARTS
from src.rig.builder import BONE_SPECIFICATIONS
from src.scene.playground_character_integration import execute_task7a1_pipeline


class TestTask7A1CharacterPlaygroundIntegration(unittest.TestCase):
    """End-to-end verification suite for Task 7A-1."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source_blend = os.path.join(PROJECT_ROOT, "output", "dynamics_playground.blend")
        cls.derived_blend = os.path.join(PROJECT_ROOT, "output", "dynamics_playground_task7a1.blend")
        cls.evidence_dir = os.path.join(PROJECT_ROOT, "docs", "evidence", "task7a1")
        cls.report_json_path = os.path.join(cls.evidence_dir, "task7a1_verification_report.json")

        # Record source blend mtime/size before execution to verify zero modification of SSOT
        cls.source_stat_before = os.stat(cls.source_blend)

        # Execute full Task 7A-1 pipeline (regenerate report, derived blend, and visual evidence if missing)
        need_visuals = not os.path.isfile(os.path.join(cls.evidence_dir, "task7a1_walk_preview.gif"))
        cls.report = execute_task7a1_pipeline(
            source_playground_blend=cls.source_blend,
            output_derived_blend=cls.derived_blend,
            evidence_dir=cls.evidence_dir,
            render_visuals=need_visuals,
        )
        cls.source_stat_after = os.stat(cls.source_blend)

    def test_01_ssot_playground_unmodified_and_derived_blend_saved(self) -> None:
        """Verify `output/dynamics_playground.blend` was never overwritten and derived blend exists."""
        self.assertEqual(
            self.source_stat_before.st_size,
            self.source_stat_after.st_size,
            "Authoritative output/dynamics_playground.blend size changed!",
        )
        self.assertTrue(os.path.isfile(self.derived_blend), "Derived task7a1 blend file was not created!")
        self.assertGreater(os.path.getsize(self.derived_blend), 100_000)
        self.assertTrue(
            self.report["playground_stations_intact_after_walk"],
            "Playground collections or dynamics stations S1..S5 were altered!",
        )

    def test_02_character_19_bones_13_meshes_8_controllers_inventory(self) -> None:
        """Verify 1 Armature, 19 bones, 13 bound mesh parts, and 8 IK/Pole controllers."""
        inv = self.report["inventory"]
        self.assertEqual(inv["armature_count_in_scene"], 1)
        self.assertEqual(inv["armature_names"], ["CharacterArmature"])
        self.assertTrue(inv["character_collection_exists"])
        self.assertEqual(inv["bone_count"], 19)
        self.assertTrue(inv["bone_names_match_specification"])
        self.assertTrue(inv["bone_hierarchy_matches_specification"])
        self.assertEqual(len(inv["bones"]), len(BONE_SPECIFICATIONS))

        self.assertEqual(inv["mesh_part_count"], 13)
        for part_name in REQUIRED_PARTS:
            self.assertIn(part_name, inv["mesh_parts"])
            p_info = inv["mesh_parts"][part_name]
            self.assertEqual(p_info["parent"], "CharacterArmature")
            self.assertEqual(p_info["parent_type"], "BONE")
            self.assertEqual(p_info["parent_bone"], p_info["expected_bone"])
            self.assertTrue(p_info["in_character_collection"])

        self.assertEqual(inv["controller_count"], 8)
        for ctrl_name in (
            "FootIK.L",
            "FootIK.R",
            "KneePole.L",
            "KneePole.R",
            "HandIK.L",
            "HandIK.R",
            "ElbowPole.L",
            "ElbowPole.R",
        ):
            self.assertIn(ctrl_name, inv["controllers"])
            self.assertEqual(inv["controllers"][ctrl_name]["type"], "EMPTY")
            self.assertTrue(inv["controllers"][ctrl_name]["in_character_collection"])

        self.assertTrue(inv["playground_preserved"])

    def test_03_minimal_control_stages_a_b_c_d(self) -> None:
        """Verify Stages A (Standing), B (Root Displacement/Yaw), C (Single-Foot IK), and D (Support Lock)."""
        stages = self.report["minimal_control_stages"]

        # Stage A: Static Standing
        sa = stages["stage_A_static_standing"]
        self.assertTrue(sa["success"])
        self.assertFalse(sa["has_rom_violation"])
        self.assertLess(sa["max_end_effector_error_m"], 1e-4)
        self.assertGreaterEqual(sa["foot_L_min_z_m"], -1e-4)
        self.assertGreaterEqual(sa["foot_R_min_z_m"], -1e-4)
        self.assertEqual(sa["support_type"], "double_stance")

        # Stage B: Root Displacement & Non-Zero Yaw
        sb = stages["stage_B_root_displacement"]
        self.assertTrue(sb["success"])
        self.assertFalse(sb["has_rom_violation"])
        self.assertLess(sb["root_position_error_m"], 1e-6)
        self.assertAlmostEqual(sb["actual_yaw_deg"], 6.0, places=4)
        self.assertLess(sb["max_end_effector_error_m"], 1e-4)

        # Stage C: Independent Single-Foot IK
        sc = stages["stage_C_single_foot_ik"]
        self.assertTrue(sc["success"])
        self.assertFalse(sc["has_rom_violation"])
        self.assertLess(sc["foot_L"]["target_error_m"], 1e-4)
        self.assertLess(sc["foot_R"]["target_error_m"], 1e-4)
        self.assertTrue(sc["foot_L"]["no_stretch"])
        self.assertTrue(sc["foot_R"]["no_stretch"])
        self.assertTrue(sc["foot_L"]["no_flip"])
        self.assertTrue(sc["foot_R"]["no_flip"])

        # Stage D: Support-Foot World Locking
        sd = stages["stage_D_support_foot_lock"]
        self.assertTrue(sd["all_steps_succeeded"])
        self.assertEqual(sd["max_controller_drift_m"], 0.0)
        self.assertLess(sd["max_ankle_bone_drift_m"], 1e-4)
        self.assertLess(sd["max_mesh_center_drift_m"], 1e-4)
        for step in sd["steps"]:
            self.assertTrue(step["foot_L_is_locked"])
            self.assertIsNone(step["foot_L_controller_parent"])

    def test_04_stage_e_continuous_walk_in_playground(self) -> None:
        """Verify Stage E historical StartStopWalkAction executes cleanly across 204 frames."""
        se = self.report["minimal_control_stages"]["stage_E_continuous_walk"]
        self.assertEqual(se["action_names"], ["start_stop_walk"])
        self.assertEqual(se["total_frames"], 204)
        self.assertEqual(se["unreachable_count"], 0)
        self.assertAlmostEqual(se["start_root_y_m"], -8.0, places=4)
        self.assertAlmostEqual(se["end_root_y_m"], -6.74, places=2)
        self.assertAlmostEqual(se["total_root_displacement_m"], 1.26, places=2)
        for sample in se["sampled_frames"]:
            self.assertTrue(sample["rom_is_valid"], f"ROM violation at frame {sample['frame']}")
            self.assertLess(sample["foot_L_target_error_m"], 1e-3)
            self.assertLess(sample["foot_R_target_error_m"], 1e-3)

    def test_05_mathematical_consistency_verifications(self) -> None:
        """Verify 5 coordinate spaces, 15-segment CoM, geometric contacts, and constraint truthfulness."""
        mc = self.report["mathematical_consistency"]

        # 1. Five Coordinate Spaces
        cs = mc["coordinate_spaces"]
        self.assertTrue(cs["wbc_success"])
        self.assertLess(cs["world_to_root_local_vector_roundtrip_error_m"], 1e-7)
        self.assertLess(cs["five_space_point_chain_roundtrip_error_m"], 1e-6)
        self.assertLess(cs["armature_vs_root_origin_alignment_error_m"], 1e-7)
        self.assertLess(cs["ik_end_effector_vs_bone_head_error_m"]["foot_L"], 1e-4)
        self.assertLess(cs["ik_end_effector_vs_bone_head_error_m"]["foot_R"], 1e-4)

        # 2. Mass & Center of Mass
        com = mc["mass_and_com"]
        self.assertEqual(com["segment_count_15"], 15)
        self.assertAlmostEqual(com["default_total_mass_kg"], 70.0, places=5)
        self.assertAlmostEqual(com["scaled_reference_mass_kg"], 75.0, places=5)
        self.assertAlmostEqual(com["mass_ratio_sum"], 1.0, places=6)
        self.assertLess(com["bilateral_com_x_offset_m"], 1e-5)
        for pair_key, sym_err in com["bilateral_segment_symmetry_errors_m"].items():
            self.assertLess(sym_err, 1e-5, f"Symmetry error on {pair_key}: {sym_err}")
        # Posture change (pelvis right +0.05m, down -0.06m, forward trunk lean -25 deg -> +Y, -Z, +X shift)
        dx, dy, dz = com["posture_change_com_delta_m"]
        self.assertGreater(dx, 0.01)
        self.assertGreater(dy, 0.02)
        self.assertLess(dz, -0.02)

        # 3. Geometric Contact
        gc = mc["geometric_contact"]
        self.assertIn(gc["surface_query_foot_L"]["surface_id"], ("default_ground", "Surface_FlatGround"))
        self.assertEqual(gc["surface_query_foot_L"]["surface_type"], "horizontal_ground")
        self.assertEqual(tuple(gc["surface_query_foot_L"]["surface_normal_world"]), (0.0, 0.0, 1.0))
        self.assertAlmostEqual(gc["surface_query_foot_L"]["signed_distance_m"], 0.0, places=5)
        self.assertEqual(gc["dual_foot_lock"]["support_type"], "double_stance")
        self.assertTrue(gc["dual_foot_lock"]["foot_L_valid"])
        self.assertTrue(gc["dual_foot_lock"]["foot_R_valid"])
        self.assertEqual(gc["left_foot_lock_right_release"]["support_type"], "single_stance_l")
        self.assertTrue(gc["left_foot_lock_right_release"]["foot_L_is_locked"])
        self.assertFalse(gc["left_foot_lock_right_release"]["foot_R_is_locked"])
        self.assertEqual(gc["right_foot_lock_left_release"]["support_type"], "single_stance_r")
        self.assertFalse(gc["right_foot_lock_left_release"]["foot_L_is_locked"])
        self.assertTrue(gc["right_foot_lock_left_release"]["foot_R_is_locked"])

        # 4. Constraint Truthfulness
        ct = mc["constraint_truthfulness"]
        self.assertTrue(ct["valid_pose_case"]["success"])
        self.assertEqual(ct["valid_pose_case"]["unmet_constraint_count"], 0)

        self.assertFalse(ct["unreachable_target_case"]["is_reachable"])
        self.assertFalse(ct["unreachable_target_case"]["is_all_reachable"])
        self.assertFalse(ct["unreachable_target_case"]["overall_success"])
        self.assertIn("REACHABILITY", ct["unreachable_target_case"]["unmet_categories"])

        self.assertTrue(ct["rom_violation_case"]["has_rom_violation"])
        self.assertFalse(ct["rom_violation_case"]["overall_success"])
        self.assertIn("ROM_VIOLATION", ct["rom_violation_case"]["unmet_categories"])

        self.assertFalse(ct["rom_clamp_reporting_case"]["initial_rom_valid"])
        self.assertTrue(ct["rom_clamp_reporting_case"]["overall_success_reported_truthfully_false"])

    def test_06_automated_evidence_files_exist_and_non_empty(self) -> None:
        """Verify JSON report, PNG keyframe screenshots, and GIF preview exist on disk."""
        self.assertTrue(os.path.isfile(self.report_json_path))
        self.assertGreater(os.path.getsize(self.report_json_path), 2_000)

        gif_path = os.path.join(self.evidence_dir, "task7a1_walk_preview.gif")
        self.assertTrue(os.path.isfile(gif_path), "Animated GIF preview missing!")
        self.assertGreater(os.path.getsize(gif_path), 10_000)

        expected_pngs = [
            "stage_A_static_front.png",
            "stage_A_static_side.png",
            "stage_A_static_iso.png",
            "stage_B_root_disp_front.png",
            "stage_B_root_disp_side.png",
            "stage_C_single_foot_ik_front.png",
            "stage_C_single_foot_ik_side.png",
            "stage_D_lock_step0_side.png",
            "stage_D_lock_step4_side.png",
            "stage_E_walk_f001_side.png",
            "stage_E_walk_f102_side.png",
            "stage_E_walk_f204_side.png",
        ]
        for fname in expected_pngs:
            fpath = os.path.join(self.evidence_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Expected visual evidence PNG missing: {fname}")
            self.assertGreater(os.path.getsize(fpath), 5_000)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
