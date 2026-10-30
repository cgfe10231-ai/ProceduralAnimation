"""ProceduralAnimation — Regression Test Suite for FIND-R2-05.

Validates the architectural contract between ContactModel geometric compliance
and instantaneous effective support qualification:
- Group A: Geometric failure causing support topology degradation (DOUBLE_STANCE -> SINGLE_STANCE_R -> FLIGHT).
- Group B: Individual geometric violation modes and boundary tolerance behavior.
- Group C: Missing measurement handling, unvalidated state isolation, and temporal invalidation.
- Group D: Multi-contact support classification covering all 8 legal support categories.
- Group E: End-to-end KinematicBridgeExecutor execution with controlled geometric failure.
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from typing import Any, Dict, List, Optional, Tuple

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
from mathutils import Matrix, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.contact_model import (
    ContactLifecycle,
    ContactRecord,
    ContactType,
    DEFAULT_LIMB_LOCAL_ANCHORS,
    EnvironmentalSurface,
    GeometricConstraintResult,
    MultiContactState,
    SupportType,
    contact_record_to_legacy_contact_point,
    enrich_motion_state_with_contacts,
)
from src.motion.framework import ContactPointState, MotionState, SurfaceQueryResult
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, setup_leg_ik


# =============================================================================
# Mock Planar Environment for Isolated Contract Testing
# =============================================================================

class MockFlatGroundEnvironment:
    """Deterministic planar ground environment for testing contact compliance."""

    def __init__(self, ground_z: float = 0.0):
        self.ground_z = ground_z

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
        return SurfaceQueryResult(
            surface_id="ground",
            surface_type="ground",
            contact_point_world=(x, y, self.ground_z),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=0.0,
            friction_coeff=0.6,
            allows_regular_support=True,
            success=True,
            source_type="analytic",
        )


# =============================================================================
# Test Suite Implementation
# =============================================================================

class TestContactModelGeometrySupportContract(unittest.TestCase):
    """Architectural contract validation for ContactModel geometry-to-support consistency."""

    # -------------------------------------------------------------------------
    # Group A: Geometric Failure & Support Type Degradation
    # -------------------------------------------------------------------------

    def test_group_a_progressive_support_degradation(self) -> None:
        """Group A: DOUBLE_STANCE -> SINGLE_STANCE_R -> FLIGHT under progressive geometric violations."""
        # Step 1: Initial double stance with two established feet at ground target
        c_l = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, 0.0, 0.0), (0, 0, 1))
        c_r = ContactRecord("g_foot_R", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, 0.0, 0.0), (0, 0, 1))
        mc = MultiContactState(contacts={"foot_L": c_l, "foot_R": c_r})

        # Evaluate both feet within allowable tolerance (5 mm normal displacement <= 15 mm)
        pos_both_valid = {"foot_L": (-0.11, 0.0, 0.005), "foot_R": (0.11, 0.0, 0.005)}
        res_a1 = mc.check_all_contacts(pos_both_valid)
        self.assertTrue(res_a1["foot_L"].is_valid)
        self.assertTrue(res_a1["foot_R"].is_valid)

        # Full support state assertions in double stance
        self.assertEqual(len(mc.active_contacts), 2)
        self.assertIn("foot_L", mc.active_contacts)
        self.assertIn("foot_R", mc.active_contacts)
        self.assertCountEqual(mc.supporting_limbs, ["foot_L", "foot_R"])
        self.assertEqual(mc.active_contact_count, 2)
        self.assertFalse(mc.is_flight)
        self.assertEqual(mc.support_type, SupportType.DOUBLE_STANCE)
        is_coplanar, poly = mc.get_coplanar_support_polygon()
        self.assertTrue(is_coplanar)
        self.assertIsNotNone(poly)
        self.assertEqual(len(poly), 2)

        # Step 2: Left foot develops 25 mm air gap (> 15 mm tolerance), right foot stays valid
        pos_l_fails = {"foot_L": (-0.11, 0.0, 0.025), "foot_R": (0.11, 0.0, 0.005)}
        res_a2 = mc.check_all_contacts(pos_l_fails)
        self.assertFalse(res_a2["foot_L"].is_valid)
        self.assertTrue(res_a2["foot_R"].is_valid)

        # Single stance right assertions
        self.assertEqual(len(mc.active_contacts), 1)
        self.assertNotIn("foot_L", mc.active_contacts)
        self.assertIn("foot_R", mc.active_contacts)
        self.assertEqual(mc.supporting_limbs, ["foot_R"])
        self.assertEqual(mc.active_contact_count, 1)
        self.assertFalse(mc.is_flight)
        self.assertEqual(mc.support_type, SupportType.SINGLE_STANCE_R)
        is_coplanar, poly = mc.get_coplanar_support_polygon()
        self.assertTrue(is_coplanar)
        self.assertIsNotNone(poly)
        self.assertEqual(len(poly), 1)
        self.assertEqual(poly[0], (0.11, 0.0))

        # Step 3: Right foot also fails (30 mm air gap) -> complete loss of support
        pos_both_fail = {"foot_L": (-0.11, 0.0, 0.025), "foot_R": (0.11, 0.0, 0.030)}
        res_a3 = mc.check_all_contacts(pos_both_fail)
        self.assertFalse(res_a3["foot_L"].is_valid)
        self.assertFalse(res_a3["foot_R"].is_valid)

        # Flight phase assertions
        self.assertEqual(len(mc.active_contacts), 0)
        self.assertEqual(mc.supporting_limbs, [])
        self.assertEqual(mc.active_contact_count, 0)
        self.assertTrue(mc.is_flight)
        self.assertEqual(mc.support_type, SupportType.FLIGHT)
        is_coplanar, poly = mc.get_coplanar_support_polygon()
        self.assertTrue(is_coplanar)
        self.assertEqual(poly, [])

    # -------------------------------------------------------------------------
    # Group B: Individual Geometric Violation Modes & Boundary Tolerances
    # -------------------------------------------------------------------------

    def test_group_b_excessive_gap(self) -> None:
        """Group B.1: Excessive air gap beyond max_allowable_gap_m (15 mm)."""
        rec = ContactRecord("c1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res = rec.check_geometric_compliance((0.0, 0.0, 0.025))
        self.assertFalse(res.is_valid)
        self.assertIn("EXCESSIVE_GAP", res.violation_reason or "")
        self.assertAlmostEqual(res.distance_normal_m, 0.025, places=5)

    def test_group_b_excessive_penetration(self) -> None:
        """Group B.2: Excessive surface penetration beyond max_allowable_penetration_m (10 mm)."""
        rec = ContactRecord("c1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res = rec.check_geometric_compliance((0.0, 0.0, -0.015))
        self.assertFalse(res.is_valid)
        self.assertIn("EXCESSIVE_PENETRATION", res.violation_reason or "")
        self.assertAlmostEqual(res.penetration_depth_m, 0.015, places=5)

    def test_group_b_excessive_slip(self) -> None:
        """Group B.3: Excessive tangential slip beyond max_allowable_slip_m (20 mm)."""
        rec = ContactRecord("c1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res = rec.check_geometric_compliance((0.025, 0.0, 0.0))
        self.assertFalse(res.is_valid)
        self.assertIn("EXCESSIVE_SLIP", res.violation_reason or "")
        self.assertAlmostEqual(res.tangential_slip_m, 0.025, places=5)

    def test_group_b_excessive_grasp_displacement(self) -> None:
        """Group B.4: Excessive 3D grasp error beyond tolerance (20 mm)."""
        rec = ContactRecord("c1", "hand_L", "bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (0, 0, 1.8), (0, 0, 1))
        res = rec.check_geometric_compliance((0.0, 0.025, 1.8))
        self.assertFalse(res.is_valid)
        self.assertIn("GRASP_DISPLACEMENT", res.violation_reason or "")
        self.assertAlmostEqual(res.total_position_error_m, 0.025, places=5)

    def test_group_b_legal_within_tolerance(self) -> None:
        """Group B.5: Compliant contact within allowable tolerance envelope."""
        rec = ContactRecord("c1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res = rec.check_geometric_compliance((0.010, 0.005, 0.008))
        self.assertTrue(res.is_valid)
        self.assertIsNone(res.violation_reason)

    def test_group_b_boundary_tolerances(self) -> None:
        """Group B.6: Exact boundary evaluation (<= tolerance is valid, > tolerance is invalid)."""
        rec = ContactRecord("c1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))

        # Gap boundary: exactly 15 mm vs 15.1 mm
        res_gap_at_limit = rec.check_geometric_compliance((0.0, 0.0, 0.015))
        self.assertTrue(res_gap_at_limit.is_valid, "Gap at exactly 15mm must be valid")
        res_gap_exceeded = rec.check_geometric_compliance((0.0, 0.0, 0.0151))
        self.assertFalse(res_gap_exceeded.is_valid, "Gap at 15.1mm must be invalid")

        # Penetration boundary: exactly 10 mm vs 10.1 mm
        res_pen_at_limit = rec.check_geometric_compliance((0.0, 0.0, -0.010))
        self.assertTrue(res_pen_at_limit.is_valid, "Penetration at exactly 10mm must be valid")
        res_pen_exceeded = rec.check_geometric_compliance((0.0, 0.0, -0.0101))
        self.assertFalse(res_pen_exceeded.is_valid, "Penetration at 10.1mm must be invalid")

        # Slip boundary: exactly 20 mm vs 20.1 mm
        res_slip_at_limit = rec.check_geometric_compliance((0.020, 0.0, 0.0))
        self.assertTrue(res_slip_at_limit.is_valid, "Slip at exactly 20mm must be valid")
        res_slip_exceeded = rec.check_geometric_compliance((0.0201, 0.0, 0.0))
        self.assertFalse(res_slip_exceeded.is_valid, "Slip at 20.1mm must be invalid")

        # Grasp boundary: exactly 20 mm vs 20.1 mm
        rec_grasp = ContactRecord("c2", "hand_L", "bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res_grasp_at_limit = rec_grasp.check_geometric_compliance((0.020, 0.0, 0.0))
        self.assertTrue(res_grasp_at_limit.is_valid, "Grasp displacement at exactly 20mm must be valid")
        res_grasp_exceeded = rec_grasp.check_geometric_compliance((0.0201, 0.0, 0.0))
        self.assertFalse(res_grasp_exceeded.is_valid, "Grasp displacement at 20.1mm must be invalid")

    # -------------------------------------------------------------------------
    # Group C: Missing Measurements & Temporal Invalidation
    # -------------------------------------------------------------------------

    def test_group_c_missing_measurement_handling(self) -> None:
        """Group C.1: Missing actual position measurements must fail deterministically, never fake 0 error."""
        c_l = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, 0.0, 0.0), (0, 0, 1))
        c_r = ContactRecord("g_foot_R", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, 0.0, 0.0), (0, 0, 1))
        mc = MultiContactState(contacts={"foot_L": c_l, "foot_R": c_r})

        # Provide measured position ONLY for foot_R, foot_L is omitted
        results = mc.check_all_contacts({"foot_R": (0.11, 0.0, 0.0)})

        self.assertFalse(results["foot_L"].is_valid)
        self.assertIn("MISSING_MEASUREMENT", results["foot_L"].violation_reason or "")
        self.assertEqual(results["foot_L"].total_position_error_m, float("inf"))
        self.assertNotIn("foot_L", mc.active_contacts)
        self.assertIn("foot_R", mc.active_contacts)
        self.assertEqual(mc.support_type, SupportType.SINGLE_STANCE_R)

    def test_group_c_unvalidated_state_isolation(self) -> None:
        """Group C.2: Unvalidated contacts cannot be assumed valid before measurement."""
        c_l = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, 0.0, 0.0), (0, 0, 1))
        self.assertIsNone(c_l.last_compliance_result)
        self.assertTrue(c_l.is_lifecycle_active)
        self.assertFalse(c_l.is_effective_support)
        self.assertFalse(c_l.is_active)

        mc = MultiContactState(contacts={"foot_L": c_l})
        self.assertEqual(len(mc.active_contacts), 0)
        self.assertTrue(mc.is_flight)
        self.assertEqual(mc.support_type, SupportType.FLIGHT)

    def test_group_c_temporal_degradation_and_recovery(self) -> None:
        """Group C.3 & C.4: Frame-to-frame failure and subsequent verified recovery."""
        c_l = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, 0.0, 0.0), (0, 0, 1))
        c_r = ContactRecord("g_foot_R", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, 0.0, 0.0), (0, 0, 1))
        mc = MultiContactState(frame=1, contacts={"foot_L": c_l, "foot_R": c_r})

        # Frame 1: Valid double stance
        mc.check_all_contacts({"foot_L": (-0.11, 0.0, 0.0), "foot_R": (0.11, 0.0, 0.0)})
        self.assertEqual(mc.support_type, SupportType.DOUBLE_STANCE)

        # Frame 2: Advances frame -> compliance reset -> foot_L develops air gap
        mc.frame = 2
        self.assertIsNone(c_l.last_compliance_result)
        self.assertIsNone(c_r.last_compliance_result)
        self.assertTrue(mc.is_flight)  # Unvalidated at frame start

        mc.check_all_contacts({"foot_L": (-0.11, 0.0, 0.035), "foot_R": (0.11, 0.0, 0.0)})
        self.assertEqual(mc.support_type, SupportType.SINGLE_STANCE_R)

        # Frame 3: foot_L re-establishes contact -> recovers to double stance
        mc.frame = 3
        mc.check_all_contacts({"foot_L": (-0.11, 0.0, 0.002), "foot_R": (0.11, 0.0, 0.002)})
        self.assertEqual(mc.support_type, SupportType.DOUBLE_STANCE)

    def test_group_c_record_mutation_invalidation(self) -> None:
        """Group C.5: Mutating target geometry invalidates cached compliance immediately."""
        c = ContactRecord("g1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res = c.check_geometric_compliance((0.0, 0.0, 0.0))
        c.set_compliance_result(res)
        self.assertTrue(c.is_effective_support)

        # Mutate target position
        c.world_position = (1.0, 2.0, 3.0)
        self.assertIsNone(c.last_compliance_result, "Mutating world_position must invalidate compliance")
        self.assertFalse(c.is_effective_support)

    def test_group_c_lifecycle_switch_to_released(self) -> None:
        """Group C.6: Transitioning ESTABLISHED -> RELEASED clears active support qualification."""
        c = ContactRecord("g1", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0, 0, 0), (0, 0, 1))
        res = c.check_geometric_compliance((0.0, 0.0, 0.0))
        c.set_compliance_result(res)
        self.assertTrue(c.is_effective_support)

        # Transition to RELEASED
        c.lifecycle = ContactLifecycle.RELEASED
        self.assertFalse(c.is_lifecycle_active)
        self.assertFalse(c.is_effective_support)
        self.assertFalse(c.is_active)
        self.assertIsNone(c.last_compliance_result)

    # -------------------------------------------------------------------------
    # Group D: Multi-Contact Support Classification
    # -------------------------------------------------------------------------

    def test_group_d_support_classifications(self) -> None:
        """Group D: Comprehensive validation of all 8 legal support categories."""
        # D1: Double stance
        c_fl = ContactRecord("fl", "foot_L", "g", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, 0, 0), (0, 0, 1))
        c_fr = ContactRecord("fr", "foot_R", "g", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, 0, 0), (0, 0, 1))
        mc = MultiContactState(contacts={"foot_L": c_fl, "foot_R": c_fr})
        mc.check_all_contacts({"foot_L": (-0.11, 0, 0), "foot_R": (0.11, 0, 0)})
        self.assertEqual(mc.support_type, SupportType.DOUBLE_STANCE)

        # D2: Single stance L and R
        mc_sl = MultiContactState(contacts={"foot_L": c_fl})
        mc_sl.check_all_contacts({"foot_L": (-0.11, 0, 0)})
        self.assertEqual(mc_sl.support_type, SupportType.SINGLE_STANCE_L)

        mc_sr = MultiContactState(contacts={"foot_R": c_fr})
        mc_sr.check_all_contacts({"foot_R": (0.11, 0, 0)})
        self.assertEqual(mc_sr.support_type, SupportType.SINGLE_STANCE_R)

        # D3: Flight
        mc_flight = MultiContactState(contacts={})
        self.assertEqual(mc_flight.support_type, SupportType.FLIGHT)

        # D4 & D5: Ledge hang (single and double hand grasp with feet free)
        c_hl = ContactRecord("hl", "hand_L", "bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (-0.2, 0, 1.8), (0, 0, 1))
        c_hr = ContactRecord("hr", "hand_R", "bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (0.2, 0, 1.8), (0, 0, 1))
        mc_hang_single = MultiContactState(contacts={"hand_L": c_hl})
        mc_hang_single.check_all_contacts({"hand_L": (-0.2, 0, 1.8)})
        self.assertEqual(mc_hang_single.support_type, SupportType.LEDGE_HANG)

        mc_hang_double = MultiContactState(contacts={"hand_L": c_hl, "hand_R": c_hr})
        mc_hang_double.check_all_contacts({"hand_L": (-0.2, 0, 1.8), "hand_R": (0.2, 0, 1.8)})
        self.assertEqual(mc_hang_double.support_type, SupportType.LEDGE_HANG)

        # D6: Hand support (unilateral support without feet)
        c_hl_uni = ContactRecord("hl_uni", "hand_L", "box", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.2, 0, 0.9), (0, 0, 1))
        mc_hand_sup = MultiContactState(contacts={"hand_L": c_hl_uni})
        mc_hand_sup.check_all_contacts({"hand_L": (-0.2, 0, 0.9)})
        self.assertEqual(mc_hand_sup.support_type, SupportType.HAND_SUPPORT)

        # D7: Multi-surface (hand touch + foot)
        mc_multi = MultiContactState(contacts={"foot_L": c_fl, "hand_R": c_hl_uni})
        mc_multi.check_all_contacts({"foot_L": (-0.11, 0, 0), "hand_R": (-0.2, 0, 0.9)})
        self.assertEqual(mc_multi.support_type, SupportType.MULTI_SURFACE)

        # D8: Wall + foot stance (ground normal vertical + wall normal horizontal)
        c_wall = ContactRecord("wall_f", "foot_R", "wall", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, 0.5, 0.3), (0, -1, 0))
        mc_wall = MultiContactState(contacts={"foot_L": c_fl, "foot_R": c_wall})
        mc_wall.check_all_contacts({"foot_L": (-0.11, 0, 0), "foot_R": (0.11, 0.5, 0.3)})
        self.assertEqual(mc_wall.support_type, SupportType.WALL_FOOT_STANCE)

        # D9: Geometrically invalid hand contact must not be counted
        mc_bad_hand = MultiContactState(contacts={"hand_L": c_hl})
        mc_bad_hand.check_all_contacts({"hand_L": (-0.2, 0.050, 1.8)})  # 50 mm error exceeds 20 mm grasp tol
        self.assertEqual(mc_bad_hand.support_type, SupportType.FLIGHT, "Invalid hand grasp must not classify as LEDGE_HANG")

    # -------------------------------------------------------------------------
    # Group E: Real KinematicBridgeExecutor Integration
    # -------------------------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        """Build character rig once for Group E Bridge tests."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cls.config = PipelineConfig()
        char_data = build_character(cls.config)
        cls.root = char_data["root"]
        cls.parts = char_data["parts"]
        cls.armature = build_rig(cls.config)
        bind_character_to_rig(cls.armature, cls.parts)
        setup_leg_ik(cls.armature)
        setup_arm_ik(cls.armature)
        cls.env = MockFlatGroundEnvironment(ground_z=0.0)

    def test_group_e_real_bridge_geometric_failure_propagation(self) -> None:
        """Group E: Real KinematicBridge execution truthfully propagates geometric failure and degrades support."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        # Controlled geometric anomaly: foot_L placed 35 mm above ground surface (ANKLE_REST_Z + 0.035m)
        # while foot_R is placed exactly at ground resting height (ANKLE_REST_Z)
        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 0.0, 0.0),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, 0.0, ANKLE_REST_Z + 0.035), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, 0.0, ANKLE_REST_Z), is_locked=True),
        )

        res = bridge.execute_frame(planned, keyframe=False)

        # 1. BridgeExecutionResult must truthfully report failure
        self.assertFalse(res.success, "Frame with 35 mm foot air gap must report success=False")

        # 2. Geometric error recorded in contact_geometry_errors
        self.assertIn("foot_L", res.contact_geometry_errors)
        geom_err_l = res.contact_geometry_errors["foot_L"]
        self.assertFalse(geom_err_l.is_valid)
        self.assertIn("EXCESSIVE_GAP", geom_err_l.violation_reason or "")

        # 3. Category CONTACT_GEOMETRY present in unmet_constraints
        has_contact_unmet = any(
            u.category == "CONTACT_GEOMETRY" and u.target_name == "foot_L"
            for u in res.unmet_constraints
        )
        self.assertTrue(has_contact_unmet, "Unmet constraints must contain CONTACT_GEOMETRY for foot_L")

        # 4. MultiContactState support classification accurately reflects ONLY valid foot_R
        mc = res.multi_contact
        self.assertIsNotNone(mc)
        self.assertEqual(mc.support_type, SupportType.SINGLE_STANCE_R)
        self.assertEqual(mc.supporting_limbs, ["foot_R"])
        self.assertEqual(mc.active_contact_count, 1)
        self.assertFalse(mc.is_flight)

        # 5. MotionState telemetry matches MultiContactState SSOT
        ms = res.motion_state
        self.assertEqual(ms.params.get("support_type"), "single_stance_r")
        self.assertEqual(ms.params.get("supporting_limbs"), ["foot_R"])
        self.assertEqual(ms.params.get("active_contact_count"), 1)

        # 6. Legacy adapter fields do NOT falsely mark failing foot_L as locked in stance
        self.assertIn("foot_L", ms.contacts)
        self.assertIn("foot_R", ms.contacts)
        self.assertFalse(ms.contacts["foot_L"].is_locked, "Invalid foot_L must NOT be marked is_locked=True")
        self.assertEqual(ms.contacts["foot_L"].phase, "swing", "Invalid foot_L must report phase='swing'")
        self.assertTrue(ms.contacts["foot_R"].is_locked, "Valid foot_R must remain is_locked=True")
        self.assertEqual(ms.contacts["foot_R"].phase, "stance", "Valid foot_R must report phase='stance'")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
