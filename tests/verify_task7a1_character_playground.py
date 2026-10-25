"""Strictly Read-Only Automated Verification & Regression Suite for Task 7A-1:
Real 19-Bone Character Integration into DynamicsPlayground, 204-Frame Reopen Validation,
Deep Scene Asset Preservation, Contact State Persistence Contract, and Negative Verification.

CRITICAL ARCHITECTURAL CONTRACT (Sections 六, 七, 八):
- This test script is 100% READ-ONLY. It NEVER invokes `execute_task7a1_pipeline()`,
  never regenerates `.blend` files, never renders images, and never overwrites JSON reports.
- If any required artifact is missing, the test fails immediately with `ARTIFACT_MISSING`.
- All 204 frames of `output/dynamics_playground_task7a1.blend` are independently reopened and evaluated
  via Blender's dependency graph (`scene.frame_set(f)` + `bpy.context.view_layer.update()`) without
  calling `MotionPlanner` or `WholeBodyController`.
- Persisted contact state is recovered directly from `scene["task7a1_contact_state_records"]`
  without re-running MotionPlanner or gait synthesis formulas.
- Includes 6 negative mutation tests proving detection gates cannot be bypassed by spoofed data.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from typing import Any, Dict

import bpy

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import REQUIRED_PARTS
from src.rig.builder import BONE_SPECIFICATIONS
from src.scene.playground_character_integration import (
    capture_deep_playground_snapshot,
    count_gif_frames,
    recover_and_verify_contact_states_from_blend,
    validate_reopened_task7a1_blend,
    verify_derived_blend_against_deep_snapshot,
)


class TestTask7A1CharacterPlaygroundIntegration(unittest.TestCase):
    """Read-only reopen verification suite for Task 7A-1 Final Acceptance Closure."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source_blend = os.path.join(PROJECT_ROOT, "output", "dynamics_playground.blend")
        cls.derived_blend = os.path.join(PROJECT_ROOT, "output", "dynamics_playground_task7a1.blend")
        cls.evidence_dir = os.path.join(PROJECT_ROOT, "docs", "evidence", "task7a1")
        cls.report_json_path = os.path.join(cls.evidence_dir, "task7a1_verification_report.json")
        cls.full_frame_json_path = os.path.join(cls.evidence_dir, "full_frame_validation.json")
        cls.contact_records_path = os.path.join(cls.evidence_dir, "task7a1_contact_state_records.json")
        cls.gif_path = os.path.join(cls.evidence_dir, "task7a1_walk_preview.gif")

        cls.watched_artifacts = [
            cls.source_blend,
            cls.derived_blend,
            cls.report_json_path,
            cls.full_frame_json_path,
            cls.contact_records_path,
            cls.gif_path,
        ]
        for path in cls.watched_artifacts:
            if not os.path.isfile(path):
                raise AssertionError(
                    f"ARTIFACT_MISSING: Required Task 7A-1 artifact does not exist: {path}. "
                    f"Run `blender --background --python run_task7a1_character_playground.py` first."
                )

        # Record exact file stats (size + mtime_ns) before read-only inspection
        cls.stats_before = {
            p: (os.stat(p).st_size, os.stat(p).st_mtime_ns) for p in cls.watched_artifacts
        }

        with open(cls.report_json_path, "r", encoding="utf-8") as f:
            cls.report = json.load(f)
        with open(cls.full_frame_json_path, "r", encoding="utf-8") as f:
            cls.saved_full_frame = json.load(f)
        with open(cls.contact_records_path, "r", encoding="utf-8") as f:
            cls.saved_contact_records = json.load(f)

        # 1. Read-only open of authoritative baseline `output/dynamics_playground.blend`
        bpy.ops.wm.open_mainfile(filepath=cls.source_blend)
        cls.deep_baseline = capture_deep_playground_snapshot(bpy.context.scene)

        # 2. Read-only deep comparison of `output/dynamics_playground_task7a1.blend` vs baseline
        cls.live_deep_diff = verify_derived_blend_against_deep_snapshot(
            deep_baseline=cls.deep_baseline,
            derived_blend_path=cls.derived_blend,
        )

        # 3. Read-only 204-frame reopen validation of `output/dynamics_playground_task7a1.blend` (in-memory, write_json=None)
        cls.live_reopen_validation = validate_reopened_task7a1_blend(
            derived_blend_path=cls.derived_blend,
            output_json_path=None,
        )

        # 4. Read-only binary inspection of the 204-frame continuous GIF
        cls.gif_info = count_gif_frames(cls.gif_path)

    def test_01_deep_scene_and_historical_asset_preservation(self) -> None:
        """Verify all 4 Playground collections, 101 protected objects, 16 surfaces, materials, and 73f S1..S5 trajectories."""
        diff = self.live_deep_diff
        self.assertEqual(diff["verdict"], "PASS")
        self.assertTrue(diff["passed"])
        self.assertEqual(diff["protected_collection_count"], 4)
        self.assertEqual(diff["protected_object_count_baseline"], 101)
        self.assertEqual(diff["protected_object_count_derived"], 101)
        self.assertEqual(diff["surface_mesh_count"], 16)
        self.assertEqual(diff["missing_collections"], [])
        self.assertEqual(diff["collection_membership_diffs"], {})
        self.assertEqual(diff["missing_protected_objects"], [])
        self.assertEqual(diff["modified_protected_objects"], {})
        self.assertEqual(diff["mesh_geometry_diffs"], {})
        self.assertEqual(diff["animation_fcurve_diffs"], {})
        self.assertEqual(diff["station_trajectory_diffs_73f"], {})
        self.assertEqual(diff["added_character_object_count"], 26)
        self.assertEqual(diff["unexpected_added_objects"], [])
        self.assertEqual(diff["missing_expected_character_objects"], [])

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

    def test_03_minimal_control_stages_a_b_c_d_and_math_consistency(self) -> None:
        """Verify Stages A-D and 5 coordinate spaces, 15-segment CoM, geometric contact, and constraint truthfulness."""
        stages = self.report["minimal_control_stages"]

        sa = stages["stage_A_static_standing"]
        self.assertTrue(sa["success"])
        self.assertFalse(sa["has_rom_violation"])
        self.assertLess(sa["max_end_effector_error_m"], 1e-4)
        self.assertGreaterEqual(sa["foot_L_min_z_m"], -1e-4)
        self.assertGreaterEqual(sa["foot_R_min_z_m"], -1e-4)
        self.assertEqual(sa["support_type"], "double_stance")

        sb = stages["stage_B_root_displacement"]
        self.assertTrue(sb["success"])
        self.assertFalse(sb["has_rom_violation"])
        self.assertLess(sb["root_position_error_m"], 1e-6)
        self.assertAlmostEqual(sb["actual_yaw_deg"], 6.0, places=4)
        self.assertLess(sb["max_end_effector_error_m"], 1e-4)

        sc = stages["stage_C_single_foot_ik"]
        self.assertTrue(sc["success"])
        self.assertFalse(sc["has_rom_violation"])
        self.assertLess(sc["foot_L"]["target_error_m"], 1e-4)
        self.assertLess(sc["foot_R"]["target_error_m"], 1e-4)
        self.assertTrue(sc["foot_L"]["no_stretch"])
        self.assertTrue(sc["foot_R"]["no_stretch"])
        self.assertTrue(sc["foot_L"]["no_flip"])
        self.assertTrue(sc["foot_R"]["no_flip"])

        sd = stages["stage_D_support_foot_lock"]
        self.assertTrue(sd["all_steps_succeeded"])
        self.assertEqual(sd["max_controller_drift_m"], 0.0)
        self.assertLess(sd["max_ankle_bone_drift_m"], 1e-4)
        self.assertLess(sd["max_mesh_center_drift_m"], 1e-4)

        mc = self.report["mathematical_consistency"]
        cs = mc["coordinate_spaces"]
        self.assertTrue(cs["wbc_success"])
        self.assertLess(cs["world_to_root_local_vector_roundtrip_error_m"], 1e-7)
        self.assertLess(cs["five_space_point_chain_roundtrip_error_m"], 1e-6)

        com = mc["mass_and_com"]
        self.assertEqual(com["segment_count_15"], 15)
        self.assertAlmostEqual(com["default_total_mass_kg"], 70.0, places=5)
        self.assertAlmostEqual(com["scaled_reference_mass_kg"], 75.0, places=5)
        self.assertAlmostEqual(com["mass_ratio_sum"], 1.0, places=6)

        ct = mc["constraint_truthfulness"]
        self.assertTrue(ct["valid_pose_case"]["success"])
        self.assertFalse(ct["unreachable_target_case"]["overall_success"])
        self.assertIn("REACHABILITY", ct["unreachable_target_case"]["unmet_categories"])
        self.assertFalse(ct["rom_violation_case"]["overall_success"])
        self.assertIn("ROM_VIOLATION", ct["rom_violation_case"]["unmet_categories"])

    def test_04_reopened_204_frame_root_and_rotation_continuity(self) -> None:
        """Verify 204-frame root translation continuity and quaternion geodesic bone rotation continuity from reopened blend."""
        val = self.live_reopen_validation
        self.assertEqual(val["verdict"], "PASS")
        self.assertTrue(val["passed"])
        self.assertEqual(val["frame_start"], 1)
        self.assertEqual(val["frame_end"], 204)
        self.assertEqual(val["total_evaluated_frames"], 204)
        self.assertEqual(len(val["frames"]), 204)
        self.assertEqual(val["fps"], 24)

        self.assertEqual(self.saved_full_frame["verdict"], "PASS")
        self.assertEqual(len(self.saved_full_frame["frames"]), 204)

        rc = val["root_translation_continuity"]
        self.assertTrue(rc["passed"])
        self.assertAlmostEqual(rc["total_displacement_m"], 1.26, places=4)
        self.assertLess(rc["stand_start_frames_1_to_13_max_step_m"], 1e-6)
        self.assertLess(rc["stand_stop_frames_193_to_204_max_step_m"], 1e-6)
        self.assertLessEqual(rc["max_single_frame_step_m"], 0.0105)
        self.assertLessEqual(rc["max_speed_vs_planned_midpoint_error_mps"], 0.005)
        self.assertLessEqual(rc["max_fd_acceleration_mps2"], 0.25)

        rot = val["bone_rotation_continuity"]
        self.assertTrue(rot["passed"])
        self.assertLess(rot["global_max_geodesic_step_deg"], 8.0)
        for bone_key in ("pelvis", "spine", "thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R"):
            self.assertIn(bone_key, rot["key_bones"])
            self.assertLess(rot["key_bones"][bone_key]["max_geodesic_step_deg"], 8.0)

    def test_05_reopened_204_frame_support_foot_and_contact_lifecycle(self) -> None:
        """Verify stance controller drift AND actual ankle bone drift across all 9 stance intervals & 8 transitions."""
        sc = self.live_reopen_validation["support_foot_and_contact_lifecycle"]
        self.assertTrue(sc["passed"])
        self.assertEqual(sc["max_stance_controller_drift_m"], 0.0)
        self.assertLess(sc["max_stance_ankle_bone_drift_m"], 1e-4)
        self.assertLess(sc["max_stance_interframe_ankle_slip_m"], 1e-4)
        self.assertLess(sc["max_ik_tracking_error_L_m"], 1e-4)
        self.assertLess(sc["max_ik_tracking_error_R_m"], 1e-4)
        self.assertGreaterEqual(sc["stance_foot_L_mesh_min_z_range_m"][0], -1e-4)
        self.assertLessEqual(sc["stance_foot_L_mesh_min_z_range_m"][1], 1e-4)
        self.assertGreaterEqual(sc["stance_foot_R_mesh_min_z_range_m"][0], -1e-4)
        self.assertLessEqual(sc["stance_foot_R_mesh_min_z_range_m"][1], 1e-4)
        self.assertGreaterEqual(sc["swing_foot_L_mesh_min_z_range_m"][0], -0.003)
        self.assertGreaterEqual(sc["swing_foot_R_mesh_min_z_range_m"][0], -0.003)
        self.assertEqual(len(sc["stance_intervals"]), 9)
        self.assertEqual(len(sc["lifecycle_transitions"]), 8)
        self.assertLess(sc["max_transition_boundary_foot_step_m"], 0.005)

    def test_06_reopened_204_frame_com_and_rigid_body_geometry(self) -> None:
        """Verify 204-frame CoM trajectory, 70.0 kg mass invariance, zero bone stretch, and zero ROM violations."""
        cg = self.live_reopen_validation["com_and_rigid_body_geometry"]
        self.assertTrue(cg["passed"])
        self.assertEqual(cg["nan_or_inf_count"], 0)
        self.assertAlmostEqual(cg["total_mass_kg_min"], 70.0, places=5)
        self.assertAlmostEqual(cg["total_mass_kg_max"], 70.0, places=5)
        self.assertAlmostEqual(cg["com_forward_y_displacement_m"], 1.26, places=3)
        self.assertGreaterEqual(cg["com_lateral_x_span_m"], 0.02)
        self.assertLessEqual(cg["com_lateral_x_span_m"], 0.12)
        self.assertLessEqual(cg["max_single_frame_com_step_m"], 0.015)
        self.assertLess(cg["max_thigh_length_error_m"], 1e-4)
        self.assertLess(cg["max_shin_length_error_m"], 1e-4)
        self.assertEqual(cg["rom_violation_frame_count"], 0)

    def test_07_continuous_204_frame_gif_and_visual_evidence(self) -> None:
        """Verify `task7a1_walk_preview.gif` contains all 204 continuous frames at 24 FPS and PNGs exist."""
        self.assertTrue(self.gif_info["exists"])
        self.assertTrue(self.gif_info["valid_header"])
        self.assertEqual(
            self.gif_info["frame_count"],
            204,
            f"Expected 204 continuous frames in GIF, found {self.gif_info['frame_count']}",
        )
        self.assertEqual(self.gif_info["uniform_delay_cs"], 4)
        self.assertGreater(self.gif_info["file_size_bytes"], 50_000)

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

    def test_08_contact_state_persistence_contract_reopen_verification(self) -> None:
        """Verify Contact State Persistence Contract (Section 六):
        - Contact state records successfully recovered from reopened .blend scene custom property.
        - Zero need for MotionPlanner or gait synthesis formula.
        - Exactly 204 contiguous frame records recovered.
        - All 9 stance intervals and 8 transitions recovered with world anchors.
        """
        bpy.ops.wm.open_mainfile(filepath=self.derived_blend)
        scene = bpy.context.scene
        recovered_meta = recover_and_verify_contact_states_from_blend(scene)

        self.assertEqual(recovered_meta["schema_version"], "1.0")
        self.assertEqual(recovered_meta["blend_asset_version"], "Task7A1_204f_v1")
        self.assertEqual(recovered_meta["total_frames"], 204)
        records = recovered_meta["records"]
        self.assertEqual(len(records), 204)

        # Verify all 9 exact stance intervals across all 204 frames
        expected_intervals = [
            (1, 12, True, True, "DOUBLE"),
            (13, 42, True, False, "LEFT"),
            (43, 66, False, True, "RIGHT"),
            (67, 90, True, False, "LEFT"),
            (91, 114, False, True, "RIGHT"),
            (115, 138, True, False, "LEFT"),
            (139, 162, False, True, "RIGHT"),
            (163, 192, True, False, "LEFT"),
            (193, 204, True, True, "DOUBLE"),
        ]
        for f_start, f_end, l_lock, r_lock, side in expected_intervals:
            for f in range(f_start, f_end + 1):
                rec = records[f - 1]
                self.assertEqual(rec["left_foot_locked"], l_lock, f"Frame {f} left lock mismatch")
                self.assertEqual(rec["right_foot_locked"], r_lock, f"Frame {f} right lock mismatch")
                self.assertEqual(rec["support_side"], side, f"Frame {f} support side mismatch")

        # Verify companion JSON matches reopened metadata
        self.assertEqual(self.saved_contact_records["blend_asset_version"], recovered_meta["blend_asset_version"])
        self.assertEqual(len(self.saved_contact_records["records"]), len(records))

    # =========================================================================
    # Negative Verification Suite (Section 八: 6 Isolated Failure Injections)
    # =========================================================================

    def test_09_negative_mesh_internal_vertex_mutation(self) -> None:
        """Negative Verification 1: Mutating an internal mesh vertex without altering bounding box
        or vertex count MUST trigger asset comparison failure in verify_derived_blend_against_deep_snapshot.
        """
        mutated_baseline = copy.deepcopy(self.deep_baseline)
        target_obj = "Surface_FlatGround"
        self.assertIn(target_obj, mutated_baseline["protected_objects"])
        me_sig = mutated_baseline["protected_objects"][target_obj]["mesh_signature"]
        self.assertIsNotNone(me_sig)

        # Mutate an internal vertex coordinate by +0.05m
        v_idx = 1
        orig_v = list(me_sig["vertices"][v_idx])
        me_sig["vertices"][v_idx] = (orig_v[0] + 0.05, orig_v[1], orig_v[2])

        diff = verify_derived_blend_against_deep_snapshot(mutated_baseline, self.derived_blend)
        self.assertFalse(diff["passed"], "Negative test failed: internal vertex mutation was not detected!")
        self.assertEqual(diff["verdict"], "FAIL")
        self.assertIn(target_obj, diff["mesh_geometry_diffs"])
        self.assertGreater(diff["mesh_geometry_diffs"][target_obj]["vertex_coordinate_mismatch_count"], 0)

    def test_10_negative_fcurve_keyframe_value_mutation(self) -> None:
        """Negative Verification 2: Mutating an F-Curve keyframe value without altering keyframe count
        MUST trigger animation curve comparison failure in verify_derived_blend_against_deep_snapshot.
        """
        mutated_baseline = copy.deepcopy(self.deep_baseline)
        target_obj = "Dynamics_AngMomArrow_S5"
        self.assertIn(target_obj, mutated_baseline["protected_objects"])
        anim_sig = mutated_baseline["protected_objects"][target_obj]["animation_signature"]
        self.assertIsNotNone(anim_sig)
        fc = anim_sig["fcurves"][0]

        # Mutate value of keyframe point 5 by +0.50
        orig_val = fc["keyframe_points"][5]["co"][1]
        fc["keyframe_points"][5]["co"] = (fc["keyframe_points"][5]["co"][0], orig_val + 0.50)

        diff = verify_derived_blend_against_deep_snapshot(mutated_baseline, self.derived_blend)
        self.assertFalse(diff["passed"], "Negative test failed: keyframe value mutation was not detected!")
        self.assertEqual(diff["verdict"], "FAIL")
        self.assertIn(target_obj, diff["animation_fcurve_diffs"])

    def test_11_negative_station_trajectory_interframe_mutation(self) -> None:
        """Negative Verification 3: Mutating dynamics station pose at inter-frame 37 (between previous
        coarse samples) MUST trigger 73-frame trajectory comparison failure.
        """
        mutated_baseline = copy.deepcopy(self.deep_baseline)
        trajs = mutated_baseline["station_trajectories_73f"]
        self.assertIn("S2", trajs)
        self.assertIn("frame_37", trajs["S2"])

        # Mutate BodyProxy location at frame 37 by +0.10m
        orig_loc = trajs["S2"]["frame_37"]["body_loc"]
        trajs["S2"]["frame_37"]["body_loc"] = (orig_loc[0], orig_loc[1] + 0.10, orig_loc[2])

        diff = verify_derived_blend_against_deep_snapshot(mutated_baseline, self.derived_blend)
        self.assertFalse(diff["passed"], "Negative test failed: inter-frame 37 trajectory mutation was not detected!")
        self.assertEqual(diff["verdict"], "FAIL")
        self.assertIn("S2_frame_37", diff["station_trajectory_diffs_73f"])

    def test_12_negative_contact_missing_frame_record(self) -> None:
        """Negative Verification 4: Deleting a frame record (e.g. frame 50) MUST trigger
        FRAME_COUNT_MISMATCH in recover_and_verify_contact_states_from_blend.
        """
        corrupted_payload = copy.deepcopy(self.saved_contact_records)
        # Delete frame 50 (index 49)
        del corrupted_payload["records"][49]
        self.assertEqual(len(corrupted_payload["records"]), 203)

        class MockScene:
            def get(self, key: str, default=None):
                if key == "task7a1_contact_state_records":
                    return json.dumps(corrupted_payload)
                return default

        with self.assertRaises(ValueError) as ctx:
            recover_and_verify_contact_states_from_blend(MockScene(), expected_frames=204)
        self.assertIn("FRAME_COUNT_MISMATCH", str(ctx.exception))

    def test_13_negative_contact_tampered_anchor(self) -> None:
        """Negative Verification 5: Tampering with a stance anchor (e.g. None or corrupted coords)
        MUST trigger TAMPERED_ANCHOR in recover_and_verify_contact_states_from_blend.
        """
        corrupted_payload = copy.deepcopy(self.saved_contact_records)
        # Tamper frame 5 (stance frame) by corrupting support_anchor_L to None
        corrupted_payload["records"][4]["support_anchor_L"] = None

        class MockScene:
            def get(self, key: str, default=None):
                if key == "task7a1_contact_state_records":
                    return json.dumps(corrupted_payload)
                return default

        with self.assertRaises(ValueError) as ctx:
            recover_and_verify_contact_states_from_blend(MockScene())
        self.assertIn("TAMPERED_ANCHOR", str(ctx.exception))

    def test_14_negative_contact_mismatched_version(self) -> None:
        """Negative Verification 6: Tampering with blend_asset_version MUST trigger
        VERSION_MISMATCH in recover_and_verify_contact_states_from_blend.
        """
        corrupted_payload = copy.deepcopy(self.saved_contact_records)
        corrupted_payload["blend_asset_version"] = "Task7A1_INVALID_v999"

        class MockScene:
            def get(self, key: str, default=None):
                if key == "task7a1_contact_state_records":
                    return json.dumps(corrupted_payload)
                return default

        with self.assertRaises(ValueError) as ctx:
            recover_and_verify_contact_states_from_blend(
                MockScene(), expected_version="Task7A1_204f_v1"
            )
        self.assertIn("VERSION_MISMATCH", str(ctx.exception))

    def test_15_readonly_verification_never_modified_artifacts(self) -> None:
        """Prove that running the test suite did not overwrite or touch any `.blend`, `.json`, or `.gif` artifact."""
        for p, (size_before, mtime_before) in self.stats_before.items():
            stat_now = os.stat(p)
            self.assertEqual(
                stat_now.st_size,
                size_before,
                f"Read-only test modified size of {p}!",
            )
            self.assertEqual(
                stat_now.st_mtime_ns,
                mtime_before,
                f"Read-only test modified timestamp of {p}!",
            )


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
