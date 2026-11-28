"""Task 7C-2 effective-contact conversion checks for Blender Headless."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.motion import closed_loop_dynamics, contact_force_solver, kinematic_bridge
from src.motion.contact_force_solver import (
    ContactConstraintSpec,
    build_contact_mapping_matrix,
    contact_mapping_multiply,
)
from src.motion.contact_model import (
    ContactLifecycle,
    ContactRecord,
    ContactType,
    GeometricConstraintResult,
    MultiContactState,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    convert_effective_contacts_to_force_constraints,
)
from tests.verify_task7b3_environment_hand_integration import (
    _execute_observed_standing_sequence,
    _sha256_file,
)
from tests.verify_task7c1_dynamics_state_conversion import R, _scene_values, _transform_vector


PLAYGROUND_BLEND = REPO_ROOT / "output" / "dynamics_playground.blend"


# [INTRODUCED 2026-11-28T19:36:40+08:00]
# TASK: TASK 7C-2
# FUNCTION: _observe_contact_sequence
# PURPOSE: Collect the original successful Bridge results and their original contact records.
# REASON: Verify genuine standing and independent arm motion through the accepted 7B-3 fixture.
def _observe_contact_sequence(**fixture_args):
    frames = []
    original_execute = KinematicBridgeExecutor.execute_frame

    def observe(bridge, *args, **kwargs):
        result = original_execute(bridge, *args, **kwargs)
        if result.success:
            frames.append((bridge, result))
        return result

    with patch.object(KinematicBridgeExecutor, "execute_frame", observe):
        fixture = _execute_observed_standing_sequence(**fixture_args)
    if len(frames) != fixture["total_frames"]:
        raise AssertionError("Each standing frame must have a successful production Bridge result")
    return fixture, frames


def _compliance(*, valid=True, distance=0.0):
    """Represent synthetic measured values for conversion-contract cases."""
    return GeometricConstraintResult(
        is_valid=valid,
        total_position_error_m=abs(distance),
        distance_normal_m=distance,
        penetration_depth_m=max(0.0, -distance),
        tangential_slip_m=0.0,
    )


def _record(limb="foot_L", contact_id="left-ground", **values):
    fields = {
        "surface_id": "floor",
        "max_allowable_gap_m": 0.03125,
        "max_allowable_penetration_m": 0.015625,
    }
    fields.update(values)
    record = ContactRecord(contact_id=contact_id, limb=limb, **fields)
    record.set_compliance_result(record.check_geometric_compliance(record.world_position))
    return record


def _state(*records):
    return MultiContactState(contacts={record.limb: record for record in records})


def _surface_records():
    return (
        _record("foot_L", "z-floor", world_position=(0.0, 0.0, 0.0),
                friction_coeff_static=0.8, surface_id="ground"),
        _record("foot_R", "a-slope", world_position=(1.0, 2.0, 0.0),
                world_normal=(0.0, 0.6, 0.8), friction_coeff_static=0.4, surface_id="ramp"),
        _record("hand_L", "m-wall", world_position=(-2.0, 1.0, 1.0),
                world_normal=(1.0, 0.0, 0.0), friction_coeff_static=0.2, surface_id="wall"),
    )


class TestTask7C2ContactConstraintConversion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_hash = _sha256_file(PLAYGROUND_BLEND)
        cls.addClassCleanup(cls._check_source_hash)
        standing, standing_frames = _observe_contact_sequence(
            standing_shoulder_L=(-0.24, -8.0, 1.505),
            standing_shoulder_R=(0.24, -8.0, 1.505),
        )
        cls.standing_bones = len(standing["env_ctx"]["armature"].pose.bones)
        cls.standing_result = standing_frames[-1][1]
        baseline = standing["frame_snapshots"][0]
        fps = standing["fps"]
        moving, cls.moving_frames = _observe_contact_sequence(
            standing_shoulder_L=baseline.shoulder_world_L,
            standing_shoulder_R=baseline.shoulder_world_R,
            left_spec={
                "ray_origin": (-0.24, -7.60, 1.85),
                "ray_direction": (0.0, 0.0, -1.0),
                "max_distance": 1.0,
                "tangent_hint": (0.0, 1.0, 0.0),
                "start_pitch_deg": 10.0,
                "start_time_sec": 2.0 / fps,
                "duration_sec": 9.0 / fps,
            },
        )
        cls.moving_bones = len(moving["env_ctx"]["armature"].pose.bones)
        cls.moving_snapshots = moving["frame_snapshots"]

    @classmethod
    def _check_source_hash(cls):
        if _sha256_file(PLAYGROUND_BLEND) != cls.source_hash:
            raise AssertionError("Source playground SHA-256 changed")

    def assert_vector_close(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, delta=1e-9)

    def assert_constraint_matches(self, constraint, record):
        self.assertIsInstance(constraint, ContactConstraintSpec)
        self.assertEqual(constraint.contact_id, record.contact_id)
        self.assertEqual(constraint.surface_id, record.surface_id)
        self.assertEqual(constraint.contact_point_world, tuple(record.world_position))
        self.assert_vector_close(constraint.surface_normal_world, record.world_normal)
        self.assertEqual(constraint.friction_coeff, record.friction_coeff_static)
        self.assertIs(constraint.is_in_contact, True)
        self.assertIs(constraint.allows_regular_support, record.metadata.get("allows_regular_support", False))
        self.assertEqual(constraint.surface_distance, record.last_compliance_result.distance_normal_m)
        self.assertEqual(constraint.contact_tolerance,
                         max(record.max_allowable_gap_m, record.max_allowable_penetration_m))
        self.assertEqual(constraint.min_normal_force, 0.0)
        self.assertEqual(constraint.max_normal_force, math.inf)

    def test_t01_real_standing_double_support(self):
        self.assertEqual(self.standing_bones, 19)
        result = self.standing_result
        self.assertTrue(result.success)
        self.assertTrue(result.wbc_result.success)
        self.assertFalse(result.wbc_result.has_rom_violation)
        state = result.multi_contact
        self.assertEqual(set(state.effective_contacts), {"foot_L", "foot_R"})
        constraints = convert_effective_contacts_to_force_constraints(state)
        self.assertIsInstance(constraints, tuple)
        self.assertEqual(len(constraints), 2)
        by_id = {constraint.contact_id: constraint for constraint in constraints}
        for record in state.effective_contacts.values():
            self.assert_constraint_matches(by_id[record.contact_id], record)

    def test_t02_real_independent_arm_ik_creates_no_force_contact(self):
        self.assertEqual(self.moving_bones, 19)
        start = self.moving_snapshots[0].actual_wrist_L
        end = self.moving_snapshots[-1].actual_wrist_L
        self.assertGreater(math.dist(start, end), 0.01)
        for _, result in self.moving_frames:
            with self.subTest(frame=result.frame):
                self.assertTrue(result.success and result.wbc_result.success)
                self.assertFalse(result.wbc_result.has_rom_violation)
                self.assertTrue(result.wbc_result.end_effectors["hand_L"].enabled)
                state = result.multi_contact
                hand = state.contacts["hand_L"]
                self.assertIs(hand.contact_type, ContactType.FREE)
                self.assertIs(hand.lifecycle, ContactLifecycle.RELEASED)
                self.assertNotIn("hand_L", state.effective_contacts)
                self.assertEqual(set(state.effective_contacts), {"foot_L", "foot_R"})
                actual_ids = tuple(c.contact_id for c in convert_effective_contacts_to_force_constraints(state))
                expected_ids = tuple(sorted(record.contact_id for record in state.effective_contacts.values()))
                self.assertEqual(actual_ids, expected_ids)

    def test_t03_lifecycle_exclusion_matrix(self):
        categories = (
            (ContactType.FREE, ContactLifecycle.ESTABLISHED),
            (ContactType.UNILATERAL, ContactLifecycle.CANDIDATE),
            (ContactType.UNILATERAL, ContactLifecycle.RELEASED),
            (ContactType.UNILATERAL, ContactLifecycle.BROKEN),
        )
        for contact_type, lifecycle in categories:
            for measured in (None, _compliance()):
                with self.subTest(contact_type=contact_type, lifecycle=lifecycle, measured=measured is not None):
                    contact = _record(contact_type=contact_type, lifecycle=lifecycle)
                    contact.set_compliance_result(measured)
                    self.assertEqual(convert_effective_contacts_to_force_constraints(_state(contact)), ())

    def test_t04_excludes_unverified_and_geometrically_invalid_contacts(self):
        for measured in (None, _compliance(valid=False, distance=0.25)):
            with self.subTest(measured=measured):
                record = _record()
                self.assertIs(record.lifecycle, ContactLifecycle.ESTABLISHED)
                record.set_compliance_result(measured)
                self.assertEqual(convert_effective_contacts_to_force_constraints(_state(record)), ())

    def test_t05_airborne_and_empty_contact_sets(self):
        unverified = _record()
        unverified.set_compliance_result(None)
        invalid = _record("hand_L", "invalid-hand")
        invalid.set_compliance_result(_compliance(valid=False))
        released = _record(lifecycle=ContactLifecycle.RELEASED)
        for state in (_state(), _state(unverified, invalid), _state(released)):
            with self.subTest(contacts=tuple(state.contacts)):
                self.assertTrue(state.is_flight)
                outcome = convert_effective_contacts_to_force_constraints(state)
                self.assertIsInstance(outcome, tuple)
                self.assertEqual(outcome, ())

    def test_t06_synthetic_unilateral_hand_contact(self):
        # This verifies the data contract with a measured synthetic wall anchor.
        record = _record("hand_L", "hand-wall", surface_id="wall",
                         world_normal=(1.0, 0.0, 0.0), world_position=(2.0, 0.5, 1.0))
        self.assertTrue(record.last_compliance_result.is_valid)
        constraint, = convert_effective_contacts_to_force_constraints(_state(record))
        self.assert_constraint_matches(constraint, record)
        self.assertFalse(constraint.allows_regular_support)

    def test_t07_floor_slope_and_wall_keep_distinct_world_geometry(self):
        records = _surface_records()
        converted = convert_effective_contacts_to_force_constraints(_state(*records))
        self.assertEqual(len(converted), 3)
        by_id = {constraint.contact_id: constraint for constraint in converted}
        for record in records:
            with self.subTest(surface=record.surface_id):
                self.assert_constraint_matches(by_id[record.contact_id], record)

    def test_t08_static_friction_surface_identity_and_support_flag(self):
        for static, dynamic, flag in ((0.0, 0.9, None), (0.8, 0.2, True), (0.3, 0.7, False)):
            with self.subTest(static=static, dynamic=dynamic, flag=flag):
                record = _record(
                    friction_coeff_static=static, friction_coeff_dynamic=dynamic,
                    surface_id="environment:retained",
                    metadata={} if flag is None else {"allows_regular_support": flag},
                )
                constraint, = convert_effective_contacts_to_force_constraints(_state(record))
                self.assert_constraint_matches(constraint, record)
                self.assertEqual(constraint.friction_coeff, static)
                self.assertEqual(constraint.surface_id, "environment:retained")
                self.assertIs(constraint.allows_regular_support, flag if flag is not None else False)

    def test_t09_signed_distance_with_asymmetric_limits(self):
        gap, penetration = 0.03125, 0.015625
        for distance in (0.0, gap / 2, -penetration / 2, gap, -penetration):
            with self.subTest(distance=distance):
                record = _record(max_allowable_gap_m=gap, max_allowable_penetration_m=penetration)
                record.set_compliance_result(_compliance(distance=distance))
                constraint, = convert_effective_contacts_to_force_constraints(_state(record))
                self.assertEqual(constraint.surface_distance, distance)
                self.assertEqual(constraint.contact_tolerance, gap)
        # Negative contradiction is inside the symmetric output tolerance but outside the source limit.
        for distance in (gap + 0.001, -(gap + penetration) / 2):
            with self.subTest(contradictory_distance=distance):
                record = _record(max_allowable_gap_m=gap, max_allowable_penetration_m=penetration)
                record.set_compliance_result(_compliance(distance=distance))
                with self.assertRaisesRegex(ValueError, "signed distance"):
                    convert_effective_contacts_to_force_constraints(_state(record))
        zero = _record(max_allowable_gap_m=0.0, max_allowable_penetration_m=0.0)
        with self.assertRaisesRegex(ValueError, "positive contact_tolerance"):
            convert_effective_contacts_to_force_constraints(_state(zero))

    def test_t10_world_translation_changes_only_constraint_positions(self):
        records = _surface_records()
        shift = (2.0, -3.0, 4.0)
        moved = []
        for record in records:
            position = tuple(p + d for p, d in zip(record.world_position, shift))
            shifted = replace(record, world_position=position)
            shifted.set_compliance_result(shifted.check_geometric_compliance(position))
            moved.append(shifted)
        original = convert_effective_contacts_to_force_constraints(_state(*records))
        actual = convert_effective_contacts_to_force_constraints(_state(*moved))
        expected = tuple(
            replace(constraint, contact_point_world=tuple(p + d for p, d in zip(constraint.contact_point_world, shift)))
            for constraint in original
        )
        self.assertEqual(actual, expected)

    def test_t11_world_rotation_preserves_constraint_covariance(self):
        records = _surface_records()
        rotated = []
        for record in records:
            position = _transform_vector(R, record.world_position)
            transformed = replace(record, world_position=position,
                                  world_normal=_transform_vector(R, record.world_normal))
            transformed.set_compliance_result(transformed.check_geometric_compliance(position))
            rotated.append(transformed)
        outcomes = convert_effective_contacts_to_force_constraints(_state(*rotated))
        self.assertEqual(len(outcomes), len(records))
        expected = {record.contact_id: record for record in records}
        for constraint in outcomes:
            record = expected[constraint.contact_id]
            self.assert_vector_close(constraint.contact_point_world, _transform_vector(R, record.world_position))
            self.assert_vector_close(constraint.surface_normal_world, _transform_vector(R, record.world_normal))
            self.assertEqual(constraint.friction_coeff, record.friction_coeff_static)
            self.assertEqual(constraint.surface_id, record.surface_id)
            self.assertEqual(constraint.surface_distance, record.last_compliance_result.distance_normal_m)

    def test_t12_rejects_invalid_structure_and_contact_identity(self):
        good = _record()
        duplicate = _record("foot_R", good.contact_id)
        cases = (
            ("wrong state", TypeError, object()),
            ("wrong record", TypeError, MultiContactState(contacts={"foot_L": object()})),
            ("non-mapping", TypeError, MultiContactState(contacts=[good])),
            ("empty ID", ValueError, _state(replace(good, contact_id=""))),
            ("non-string ID", TypeError, _state(replace(good, contact_id=1))),
            ("duplicate effective ID", ValueError, _state(good, duplicate)),
            ("wrong limb type", TypeError, MultiContactState(contacts={"foot_L": replace(good, limb=1)})),
            ("wrong key type", TypeError, MultiContactState(contacts={1: good})),
            ("mismatched limb key", ValueError, MultiContactState(contacts={"foot_R": good})),
            ("empty limb", ValueError, _state(replace(good, limb=""))),
            ("string contact type", TypeError, _state(replace(good, contact_type="unilateral"))),
            ("string lifecycle", TypeError, _state(replace(good, lifecycle="established"))),
            ("wrong compliance type", TypeError, _state(replace(good, last_compliance_result={}))),
            ("non-bool compliance flag", TypeError, _state(replace(good, last_compliance_result=_compliance(valid=1)))),
            ("non-bool support flag", TypeError, _state(replace(good, metadata={"allows_regular_support": 1}))),
            ("empty surface ID", ValueError, _state(replace(good, surface_id=""))),
        )
        for label, error_type, state in cases:
            with self.subTest(label=label):
                with self.assertRaises(error_type) as error:
                    convert_effective_contacts_to_force_constraints(state)
                self.assertTrue(str(error.exception))

    def test_t13_rejects_non_finite_and_nonphysical_input_values(self):
        cases = (
            ("world_position", (math.nan, 0.0, 0.0), ValueError),
            ("world_position", (0.0, math.inf, 0.0), ValueError),
            ("world_position", (True, 0.0, 0.0), TypeError),
            ("world_position", (0.0, 1.0), ValueError),
            ("world_normal", (0.0, math.nan, 1.0), ValueError),
            ("world_normal", (math.inf, 0.0, 1.0), ValueError),
            ("world_normal", (0.0, 0.0, 0.0), ValueError),
            ("world_normal", (0.0, 0.0, 2.0), ValueError),
            ("world_normal", (1.0, 0.0, 0.0, 0.0), ValueError),
            ("world_normal", (False, 0.0, 1.0), TypeError),
            ("friction_coeff_static", True, TypeError),
            ("friction_coeff_static", -0.2, ValueError),
            ("friction_coeff_static", math.nan, ValueError),
            ("friction_coeff_static", math.inf, ValueError),
            ("distance_normal_m", math.nan, ValueError),
            ("distance_normal_m", -math.inf, ValueError),
            ("distance_normal_m", True, TypeError),
            ("distance_normal_m", "0", TypeError),
            ("max_allowable_gap_m", -0.01, ValueError),
            ("max_allowable_gap_m", math.nan, ValueError),
            ("max_allowable_penetration_m", math.inf, ValueError),
            ("max_allowable_penetration_m", True, TypeError),
        )
        for name, value, error_type in cases:
            with self.subTest(field=name, value=value):
                record = _record()
                # Keep the corrupt snapshot effective and pass raw bad data past constructor normalization.
                if name == "distance_normal_m":
                    record.set_compliance_result(replace(record.last_compliance_result, distance_normal_m=value))
                    received = record.last_compliance_result.distance_normal_m
                else:
                    object.__setattr__(record, name, value)
                    received = getattr(record, name)
                self.assertIs(received, value)
                self.assertTrue(record.last_compliance_result.is_valid)
                with self.assertRaises(error_type) as error:
                    convert_effective_contacts_to_force_constraints(_state(record))
                self.assertIn("Contact", str(error.exception))

    def test_t14_effective_grasp_is_rejected_without_partial_results(self):
        grasp = _record("hand_L", "bar-grasp", contact_type=ContactType.GRASP)
        foot = _record()
        for state in (_state(grasp), _state(foot, grasp)):
            with self.subTest(contacts=tuple(state.contacts)):
                self.assertIn("hand_L", state.effective_contacts)
                with self.assertRaisesRegex(ValueError, r"UNSUPPORTED_CONTACT_TYPE.*GRASP.*bar-grasp"):
                    convert_effective_contacts_to_force_constraints(state)
        invalid = replace(grasp, last_compliance_result=_compliance(valid=False))
        released = replace(grasp, lifecycle=ContactLifecycle.RELEASED)
        for record in (invalid, released):
            with self.subTest(lifecycle=record.lifecycle, compliance=record.last_compliance_result):
                self.assertEqual(convert_effective_contacts_to_force_constraints(_state(record)), ())
                result = convert_effective_contacts_to_force_constraints(_state(foot, record))
                self.assertEqual(tuple(contact.contact_id for contact in result), (foot.contact_id,))

    def test_t15_sorted_constraints_feed_existing_wrench_mapping(self):
        records = (*_surface_records(), _record("hand_R", "b-ledge", world_position=(0.0, 1.0, 3.0),
                                               world_normal=(0.0, -1.0, 0.0), surface_id="ledge"))
        forward = convert_effective_contacts_to_force_constraints(_state(*records))
        backward = convert_effective_contacts_to_force_constraints(_state(*reversed(records)))
        self.assertIsInstance(forward, tuple)
        self.assertEqual(forward, backward)
        self.assertEqual(tuple(c.contact_id for c in forward), tuple(sorted(record.contact_id for record in records)))

        com = (0.5, -1.0, 2.0)
        forces = {
            "z-floor": (1.0, 3.0, 2.0), "a-slope": (-2.0, 1.0, 4.0),
            "m-wall": (8.0, -2.0, -1.0), "b-ledge": (4.0, -5.0, 3.0),
        }
        actual_force, actual_torque = contact_mapping_multiply(
            build_contact_mapping_matrix(forward, com),
            [forces[constraint.contact_id] for constraint in forward],
        )
        force = tuple(math.fsum(value[i] for value in forces.values()) for i in range(3))
        moments = []
        for record in records:
            x, y, z = (p - c for p, c in zip(record.world_position, com))
            fx, fy, fz = forces[record.contact_id]
            moments.append((y * fz - z * fy, z * fx - x * fz, x * fy - y * fx))
        torque = tuple(math.fsum(moment[i] for moment in moments) for i in range(3))
        self.assert_vector_close(actual_force, force)
        self.assert_vector_close(actual_torque, torque)

    def test_t16_deterministic_immutable_and_read_only(self):
        bridge, result = self.moving_frames[-1]
        state = result.multi_contact
        before_input = deepcopy(state)
        identities = {key: (record, record.last_compliance_result, record.metadata)
                      for key, record in state.contacts.items()}
        bridge_values = (bridge._last_frame, bridge._last_time_sec, bridge.last_multi_contact,
                         bridge.last_active_limb_targets)
        before_bridge = deepcopy(bridge_values)
        before_scene = _scene_values()
        self.assertTrue(any(curve[2] for _, curves in before_scene[-1] for curve in curves))
        forbidden = AssertionError("Conversion tried to access geometry, solve forces or run dynamics")
        with (
            patch.object(ContactRecord, "check_geometric_compliance", side_effect=forbidden),
            patch.object(bridge.environment, "query_spatial_surface", side_effect=forbidden),
            patch.object(bridge.environment, "query_surface_at_point", side_effect=forbidden),
            patch.object(bridge.environment, "query_ground_support_at", side_effect=forbidden),
            patch.object(contact_force_solver, "solve_contact_forces", side_effect=forbidden),
            patch.object(contact_force_solver, "create_contact_constraint_from_environment", side_effect=forbidden),
            patch.object(closed_loop_dynamics, "step_closed_loop_dynamics", side_effect=forbidden),
            patch.object(kinematic_bridge, "bpy", None),
        ):
            outputs = [convert_effective_contacts_to_force_constraints(state) for _ in range(100)]

        canonical = outputs[0]
        self.assertTrue(canonical)
        self.assertTrue(all(value == canonical for value in outputs))
        self.assertIsInstance(canonical, tuple)
        with self.assertRaises(TypeError):
            canonical[0] = canonical[0]
        with self.assertRaises(FrozenInstanceError):
            canonical[0].friction_coeff = 9.0
        self.assertIsInstance(canonical[0].contact_point_world, tuple)
        self.assertIsInstance(canonical[0].surface_normal_world, tuple)
        self.assertEqual(state, before_input)
        for key, record in state.contacts.items():
            original, compliance, metadata = identities[key]
            self.assertIs(record, original)
            self.assertIs(record.last_compliance_result, compliance)
            self.assertIs(record.metadata, metadata)
        self.assertEqual((bridge._last_frame, bridge._last_time_sec, bridge.last_multi_contact,
                          bridge.last_active_limb_targets), before_bridge)
        self.assertIs(bridge.last_multi_contact, bridge_values[2])
        self.assertIs(bridge.last_active_limb_targets, bridge_values[3])
        self.assertEqual(_scene_values(), before_scene)
        self.assertEqual(_sha256_file(PLAYGROUND_BLEND), self.source_hash)


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1:])
    unittest.main(argv=argv, verbosity=2)
