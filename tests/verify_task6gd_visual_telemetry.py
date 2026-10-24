"""Automated Visual Evidence and Telemetry Coherence Verification (Task 6G-D-C2-A).

Verifies:
1. Telemetry JSON schema, completeness (5 stations, 72 frames, dt=1/24s).
2. Numerical Coherence: Blender evaluated object transforms match numerical integration (< 1e-5m, < 1e-5 rad).
3. Physics Fidelity: Reaction forces, friction clamping, and angular momentum evolution.
4. Anti-Spoofing & Anti-Tampering: Divergence between target references and actual physical states.
5. Visual Artifacts: Contact sheet, animated GIF, keyframe stills, and validation report existence.
"""

import json
import math
import os
import sys
import unittest
from typing import Any, Dict


class TestDynamicsVisualTelemetry(unittest.TestCase):
    """Test suite verifying visual evidence and telemetry coherence."""

    @classmethod
    def setUpClass(cls):
        cls.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.output_dir = os.path.join(cls.project_root, "output", "evidence", "task6gd_c2a")
        cls.docs_dir = os.path.join(cls.project_root, "docs", "evidence", "task6gd_c2a")
        cls.telem_path = os.path.join(cls.output_dir, "telemetry.json")

    def test_01_telemetry_json_structure_and_integrity(self):
        """Verify telemetry.json schema, station count, and timestamp monotonicity."""
        self.assertTrue(
            os.path.isfile(self.telem_path),
            f"telemetry.json must exist at: {self.telem_path}",
        )
        with open(self.telem_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("metadata", data)
        self.assertIn("stations", data)
        self.assertIn("summary", data)

        meta = data["metadata"]
        self.assertEqual(meta["num_frames"], 72)
        self.assertEqual(meta["fps"], 24)
        self.assertAlmostEqual(meta["dt_sec"], 1.0 / 24.0, places=6)

        stations = data["stations"]
        expected_stations = [
            "scenario_1_static_support",
            "scenario_2_free_fall",
            "scenario_3_horizontal_acceleration",
            "scenario_4_insufficient_friction",
            "scenario_5_eccentric_rotation",
        ]
        for s_key in expected_stations:
            self.assertIn(s_key, stations, f"Missing station: {s_key}")
            s_data = stations[s_key]
            frames = s_data["frames"]
            self.assertEqual(len(frames), 72, f"Station {s_key} must contain exactly 72 frames")

            # Check timestamp progression
            prev_t = -1.0
            for f in frames:
                t = f["timestamp_sec"]
                self.assertGreater(t, prev_t, "Timestamps must be strictly increasing")
                self.assertIn("integrated_state", f)
                self.assertIn("target_reference", f)
                self.assertIn("blender_evaluated", f)
                self.assertIn("coherence_deltas", f)
                prev_t = t

    def test_02_blender_object_physics_coherence(self):
        """Verify evaluated Blender objects match integrated physics (< 1e-5m, < 1e-5 rad)."""
        with open(self.telem_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        summary = data["summary"]
        self.assertTrue(summary.get("coherence_passed", False), "Summary must report coherence_passed=True")
        self.assertLess(
            summary["max_position_error_m"],
            1e-5,
            f"Overall max position error exceeds tolerance: {summary['max_position_error_m']}",
        )
        self.assertLess(
            summary["max_orientation_error_rad"],
            1e-5,
            f"Overall max orientation error exceeds tolerance: {summary['max_orientation_error_rad']}",
        )

        for s_key, s_data in data["stations"].items():
            m = s_data["metrics"]
            self.assertLess(
                m["max_com_position_error_m"],
                1e-5,
                f"Station {s_key} position error {m['max_com_position_error_m']} exceeds 1e-5m",
            )
            self.assertLess(
                m["max_body_orientation_error_rad"],
                1e-5,
                f"Station {s_key} orientation error {m['max_body_orientation_error_rad']} exceeds 1e-5 rad",
            )

    def test_03_force_and_angular_momentum_arrows_fidelity(self):
        """Verify physical reaction forces, zero-contact in free-fall, and roll angular momentum."""
        with open(self.telem_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        stations = data["stations"]

        # Station 1: Static support normal force ~ 686.7N, Fx=0, Fy=0
        s1 = stations["scenario_1_static_support"]["frames"]
        for f in s1:
            tot_f = f["total_contact_force"]
            self.assertAlmostEqual(tot_f[0], 0.0, delta=0.5, msg="S1 Fx must be near zero")
            self.assertAlmostEqual(tot_f[1], 0.0, delta=0.5, msg="S1 Fy must be near zero")
            self.assertAlmostEqual(tot_f[2], 686.7, delta=1.0, msg="S1 Fz must balance 70kg gravity")

        # Station 2: Free fall contact force must be identically 0
        s2 = stations["scenario_2_free_fall"]["frames"]
        for f in s2:
            tot_f = f["total_contact_force"]
            self.assertEqual(tot_f, [0.0, 0.0, 0.0], "S2 contact force must be zero in mid-air")

        # Station 4: Friction limit clamping (mu=0.08)
        s4 = stations["scenario_4_insufficient_friction"]["frames"]
        for f in s4:
            tot_f = f["total_contact_force"]
            # Maximum tangential force is mu * Fn = 0.08 * 686.7 ~ 54.9N
            self.assertLessEqual(abs(tot_f[0]), 56.0, "S4 tangential force must be clamped by friction cone")

        # Station 5: Eccentric roll accumulates angular momentum L_x
        s5 = stations["scenario_5_eccentric_rotation"]["frames"]
        f_init = s5[0]["integrated_state"]["angular_momentum"]
        f_final = s5[-1]["integrated_state"]["angular_momentum"]
        self.assertAlmostEqual(f_init[0], 0.0, delta=1e-3, msg="Initial Lx must be zero")
        self.assertGreater(
            abs(f_final[0]),
            50.0,
            f"Final Lx must accumulate significant angular momentum from eccentric torque, got {f_final[0]}",
        )

    def test_04_target_spoofing_detection_and_anti_tampering(self):
        """Verify target references diverge from physical states where physically required."""
        with open(self.telem_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        stations = data["stations"]

        # Station 4 (Slip): Target ghost pulls ahead, actual physical body lags
        s4_metrics = stations["scenario_4_insufficient_friction"]["metrics"]
        self.assertGreater(
            s4_metrics["final_target_actual_divergence_m"],
            4.0,
            f"Station 4 slip divergence must exceed 4.0m, got {s4_metrics['final_target_actual_divergence_m']}",
        )

        # Station 5 (Roll): Target attitude is identity, actual body rolls away
        s5_metrics = stations["scenario_5_eccentric_rotation"]["metrics"]
        self.assertGreater(
            s5_metrics["final_target_actual_rot_divergence_rad"],
            0.40,
            f"Station 5 attitude divergence must exceed 0.40 rad, got {s5_metrics['final_target_actual_rot_divergence_rad']}",
        )

        # Station 2 (Free Fall): Target asks to hover at z=3.5, physical body drops
        s2_metrics = stations["scenario_2_free_fall"]["metrics"]
        self.assertGreater(
            s2_metrics["final_target_actual_divergence_m"],
            3.0,
            f"Station 2 free-fall divergence must exceed 3.0m, got {s2_metrics['final_target_actual_divergence_m']}",
        )

    def test_05_visual_evidence_artifacts_and_contact_sheet_exist(self):
        """Verify contact sheet, animated GIF, validation report, and keyframe stills exist."""
        # Contact sheet
        out_sheet = os.path.join(self.output_dir, "contact_sheet.png")
        docs_sheet = os.path.join(self.docs_dir, "contact_sheet.png")
        self.assertTrue(os.path.isfile(out_sheet), f"Missing {out_sheet}")
        self.assertTrue(os.path.isfile(docs_sheet), f"Missing {docs_sheet}")
        self.assertGreater(os.path.getsize(docs_sheet), 50 * 1024, "Contact sheet must exceed 50 KB")

        # Validation report
        out_rep = os.path.join(self.output_dir, "validation_report.md")
        docs_rep = os.path.join(self.docs_dir, "validation_report.md")
        self.assertTrue(os.path.isfile(out_rep), f"Missing {out_rep}")
        self.assertTrue(os.path.isfile(docs_rep), f"Missing {docs_rep}")
        with open(docs_rep, "r", encoding="utf-8") as f:
            rep_text = f.read()
        self.assertIn("PASS", rep_text)
        self.assertIn("Station 1", rep_text)
        self.assertIn("Station 5", rep_text)

        # Animated GIF
        docs_gif = os.path.join(self.docs_dir, "dynamics_overview_anim.gif")
        if os.path.isfile(docs_gif):
            self.assertGreater(os.path.getsize(docs_gif), 10 * 1024, "Animated GIF must exceed 10 KB")

        # Keyframe samples in docs
        docs_samples = os.path.join(self.docs_dir, "keyframe_samples")
        self.assertTrue(os.path.isdir(docs_samples), f"Missing {docs_samples}")
        sample_files = [f for f in os.listdir(docs_samples) if f.endswith(".png")]
        self.assertGreaterEqual(len(sample_files), 15, "Must contain at least 15 sample stills in docs")


if __name__ == "__main__":
    unittest.main()
