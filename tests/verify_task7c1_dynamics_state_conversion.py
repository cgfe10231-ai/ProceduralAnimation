"""Task 7C-1 verification through the existing 19-bone production pipeline.

Run with Blender 5.1.1 only after independent approval. Arguments after the
Blender separator are forwarded to unittest, including --failfast.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import bpy
from mathutils import Quaternion

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.motion.body_inertia import InertiaTensor
from src.motion.body_kinematics import BodyKinematicsTracker
from src.motion.forward_dynamics import ForwardDynamicsState
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    convert_body_motion_to_dynamics_state,
)
from src.scene.playground_asset_preservation import get_action_fcurves
from tests.verify_task7b3_environment_hand_integration import (
    _execute_observed_standing_sequence,
    _sha256_file,
)


PLAYGROUND_BLEND = REPO_ROOT / "output" / "dynamics_playground.blend"
# Independent analytic reference for the active rotation with q=(1,2,3,4)/sqrt(30).
Q = tuple(component / math.sqrt(30) for component in (1, 2, 3, 4))
R = (
    (-2 / 3, 2 / 15, 11 / 15),
    (2 / 3, -1 / 3, 2 / 3),
    (1 / 3, 14 / 15, 2 / 15),
)
REFERENCE_INERTIA = InertiaTensor(4.0, 5.0, 6.0, 0.3, -0.4, 0.2)


# [INTRODUCED 2026-11-28T17:50:37+08:00]
# TASK: TASK 7C-1
# FUNCTION: _capture_sequence
# PURPOSE: Capture the original committed Tracker sample and Bridge result for each successful production frame.
# REASON: Use real 19-bone kinematics and inertia in T01, T08 and the read-only checks.
def _capture_sequence(**fixture_args):
    samples = []
    successful_frames = []
    original_sample = BodyKinematicsTracker.sample_and_update
    original_execute = KinematicBridgeExecutor.execute_frame

    def observe_sample(tracker, *args, **kwargs):
        motion = original_sample(tracker, *args, **kwargs)
        samples.append((tracker, motion))
        return motion

    def observe_frame(bridge, *args, **kwargs):
        count = len(samples)
        result = original_execute(bridge, *args, **kwargs)
        if result.success:
            if len(samples) != count + 1:
                raise AssertionError("A successful Bridge frame must produce one Tracker sample")
            tracker, motion = samples[count]
            inertia = result.inertia_state
            if inertia is None or result.frame != motion.pose.frame or result.frame != inertia.frame:
                raise AssertionError("Bridge, Tracker and inertia sample must refer to the same frame")
            successful_frames.append((tracker, motion, inertia, result.wbc_result))
        return result

    with (
        patch.object(BodyKinematicsTracker, "sample_and_update", observe_sample),
        patch.object(KinematicBridgeExecutor, "execute_frame", observe_frame),
    ):
        fixture = _execute_observed_standing_sequence(**fixture_args)
    if len(successful_frames) != fixture["total_frames"]:
        raise AssertionError("Expected one successful sample per frame of the standing sequence")
    return fixture, successful_frames


def _transform_vector(rotation, vector):
    return tuple(math.fsum(a * b for a, b in zip(row, vector)) for row in rotation)


def _transform_tensor(rotation, tensor):
    """Evaluate each component of R I Rᵀ independently in float64."""
    return tuple(
        tuple(
            math.fsum(rotation[i][k] * tensor[k][l] * rotation[j][l]
                      for k in range(3) for l in range(3))
            for j in range(3)
        )
        for i in range(3)
    )


def _scene_values():
    """Read only the live scene state inspected before and after conversion."""
    scene = bpy.context.scene
    objects = tuple(
        (obj.name, obj.as_pointer(), obj.type,
         obj.parent.name if obj.parent is not None else None,
         tuple(tuple(row) for row in obj.matrix_world),
         tuple((bone.name, tuple(tuple(row) for row in bone.matrix),
                tuple(tuple(row) for row in bone.matrix_basis))
               for bone in obj.pose.bones) if obj.type == "ARMATURE" else (),
         obj.animation_data.action.name
         if obj.animation_data is not None and obj.animation_data.action is not None else None)
        for obj in sorted(scene.objects, key=lambda item: item.name)
    )
    actions = tuple(
        (action.name, tuple(
            (curve.data_path, curve.array_index, tuple(
                (tuple(point.co), tuple(point.handle_left), tuple(point.handle_right),
                 point.interpolation)
                for point in curve.keyframe_points
            ))
            for curve in get_action_fcurves(action)
        ))
        for action in sorted(bpy.data.actions, key=lambda item: item.name)
    )
    return (scene.name, scene.frame_current, scene.frame_subframe, objects, actions)


class TestTask7C1DynamicsStateConversion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_hash = _sha256_file(PLAYGROUND_BLEND)
        cls.addClassCleanup(cls._verify_source_hash)
        fixture, cls.standing_frames = _capture_sequence(
            standing_shoulder_L=(-0.24, -8.0, 1.505),
            standing_shoulder_R=(0.24, -8.0, 1.505),
        )
        cls.standing_bone_count = len(fixture["env_ctx"]["armature"].pose.bones)
        first_frame = fixture["frame_snapshots"][0]
        fps = fixture["fps"]
        # Reuse the accepted 7B-3 left IK standing reach against the platform.
        active, cls.moving_frames = _capture_sequence(
            standing_shoulder_L=first_frame.shoulder_world_L,
            standing_shoulder_R=first_frame.shoulder_world_R,
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
        cls.moving_bone_count = len(active["env_ctx"]["armature"].pose.bones)
        _, cls.standing_motion, cls.standing_inertia, _ = cls.standing_frames[1]
        reach = active["acq_L"]
        start_time = reach["start_time_sec"]
        end_time = start_time + reach["duration_sec"]
        cls.moving_frame = max(
            (frame for frame in cls.moving_frames if start_time < frame[1].pose.time_sec < end_time),
            key=lambda frame: frame[2].angular_momentum_magnitude,
        )

    @classmethod
    def _verify_source_hash(cls):
        if _sha256_file(PLAYGROUND_BLEND) != cls.source_hash:
            raise AssertionError("The source playground SHA-256 changed during Task 7C-1")

    def assert_vector_close(self, actual, expected, *, tolerance=1e-6):
        self.assertEqual(len(actual), len(expected))
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertTrue(math.isclose(a, b, abs_tol=tolerance, rel_tol=tolerance),
                            f"component {index}: {a} != {b}")

    def assert_tensor_close(self, actual, expected, *, tolerance=1e-6):
        for actual_row, expected_row in zip(actual, expected, strict=True):
            self.assert_vector_close(actual_row, expected_row, tolerance=tolerance)

    def assert_rotation_equivalent(self, actual, expected):
        self.assertAlmostEqual(abs(math.fsum(a * b for a, b in zip(actual, expected))), 1.0, delta=1e-6)

    def test_t01_actual_stationary_19_bone_state(self):
        self.assertEqual(self.standing_bone_count, 19)
        motion, inertia = self.standing_motion, self.standing_inertia
        state = convert_body_motion_to_dynamics_state(motion, inertia)
        self.assertIsInstance(state, ForwardDynamicsState)
        self.assertEqual(motion.pose.frame, inertia.frame)
        self.assertGreater(motion.pose.frame, self.standing_frames[0][1].pose.frame)
        self.assertEqual(state.mass, inertia.total_mass_kg)
        self.assertEqual(state.com_position_world, inertia.com_world)
        self.assert_vector_close(state.com_velocity_world, (0.0, 0.0, 0.0), tolerance=1e-5)
        self.assert_vector_close(state.angular_momentum_about_com_world, (0.0, 0.0, 0.0), tolerance=1e-5)
        self.assert_rotation_equivalent(state.orientation_quat_world, motion.pose.root_orientation_quat)
        self.assertTrue(state.inertia_tensor_body.is_positive_definite())

    def test_t02_authoritative_mass_com_time_and_linear_momentum(self):
        _, motion, inertia, _ = self.moving_frame
        state = convert_body_motion_to_dynamics_state(motion, inertia)
        self.assertEqual(state.timestamp, motion.pose.time_sec)
        self.assertEqual(state.mass, inertia.total_mass_kg)
        self.assertEqual(state.com_position_world, inertia.com_world)
        self.assertEqual(state.com_velocity_world, motion.velocity.com_linear_velocity)
        self.assertEqual(state.angular_momentum_about_com_world, inertia.angular_momentum_body_com)
        self.assertGreater(math.hypot(*state.com_velocity_world), 0.0)
        expected_momentum = tuple(inertia.total_mass_kg * v for v in motion.velocity.com_linear_velocity)
        self.assertEqual(state.linear_momentum_world, expected_momentum)

    def test_t03_world_to_body_inertia_with_non_axis_aligned_attitude(self):
        inertia = replace(self.standing_inertia, inertia_tensor_body_com=REFERENCE_INERTIA)
        world_matrix = REFERENCE_INERTIA.to_tuple()
        expected = _transform_tensor(tuple(zip(*R)), world_matrix)
        for attitude in (Q, tuple(-v for v in Q), tuple(v * (1.0 + 5e-7) for v in Q)):
            with self.subTest(attitude=attitude):
                motion = replace(self.standing_motion, pose=replace(self.standing_motion.pose,
                                                                  root_orientation_quat=attitude))
                state = convert_body_motion_to_dynamics_state(motion, inertia)
                self.assert_rotation_equivalent(state.orientation_quat_world, Q)
                self.assert_tensor_close(state.inertia_tensor_body.to_matrix(), expected, tolerance=1e-9)
        self.assertGreater(abs(expected[0][1] - world_matrix[0][1]), 0.1)

    def test_t04_body_to_world_round_trip(self):
        motion = replace(self.standing_motion, pose=replace(self.standing_motion.pose, root_orientation_quat=Q))
        inertia = replace(self.standing_inertia, inertia_tensor_body_com=REFERENCE_INERTIA)
        world_matrix = REFERENCE_INERTIA.to_tuple()
        state = convert_body_motion_to_dynamics_state(motion, inertia)
        reconstructed = state.inertia_tensor_world.to_matrix()
        tolerance = 1e-9 * max(1.0, math.hypot(*(value for row in world_matrix for value in row)))
        max_error = max(abs(a - b) for rows in zip(reconstructed, world_matrix) for a, b in zip(*rows))
        self.assertLessEqual(max_error, tolerance)

    def test_t05_world_translation_covariance(self):
        _, motion, inertia, _ = self.moving_frame
        shift = (3.0, -4.0, 5.0)

        def translate(vector):
            return tuple(v + d for v, d in zip(vector, shift))

        moved_pose = replace(
            motion.pose, root_position=translate(motion.pose.root_position),
            pelvis_position=translate(motion.pose.pelvis_position), com_world=translate(motion.pose.com_world),
            segment_positions={key: translate(p) for key, p in motion.pose.segment_positions.items()},
            end_effectors={key: translate(p) for key, p in motion.pose.end_effectors.items()},
        )
        moved_inertia = replace(
            inertia, com_world=translate(inertia.com_world),
            segments={key: replace(seg, world_com=translate(seg.world_com))
                      for key, seg in inertia.segments.items()},
        )
        before = convert_body_motion_to_dynamics_state(motion, inertia)
        after = convert_body_motion_to_dynamics_state(replace(motion, pose=moved_pose), moved_inertia)
        self.assertEqual(after.com_position_world, translate(before.com_position_world))
        self.assertEqual(after.com_velocity_world, before.com_velocity_world)
        self.assertEqual(after.angular_momentum_about_com_world, before.angular_momentum_about_com_world)
        self.assertEqual(after.inertia_tensor_body, before.inertia_tensor_body)
        self.assertEqual(after.timestamp, before.timestamp)
        self.assertEqual(after.mass, before.mass)

    def test_t06_global_rotation_covariance_preserves_body_inertia(self):
        _, motion, inertia, _ = self.moving_frame
        pose = replace(motion.pose, root_orientation_quat=(1.0, 0.0, 0.0, 0.0))
        velocity = motion.velocity
        inertia = replace(inertia, inertia_tensor_body_com=REFERENCE_INERTIA)

        def rotate(vector):
            return _transform_vector(R, vector)

        rotated_pose = replace(
            pose, root_position=rotate(pose.root_position), root_orientation_quat=Q,
            pelvis_position=rotate(pose.pelvis_position), com_world=rotate(pose.com_world),
            segment_positions={key: rotate(value) for key, value in pose.segment_positions.items()},
            segment_orientations={key: tuple(Quaternion(Q) @ Quaternion(value))
                                  for key, value in pose.segment_orientations.items()},
            end_effectors={key: rotate(value) for key, value in pose.end_effectors.items()},
        )
        rotated_velocity = replace(
            velocity, root_linear_velocity=rotate(velocity.root_linear_velocity),
            com_linear_velocity=rotate(velocity.com_linear_velocity),
            segment_linear_velocities={key: rotate(value) for key, value in velocity.segment_linear_velocities.items()},
            segment_angular_velocities={key: rotate(value) for key, value in velocity.segment_angular_velocities.items()},
        )
        rotated_inertia = replace(
            inertia, com_world=rotate(inertia.com_world), com_linear_velocity=rotate(inertia.com_linear_velocity),
            angular_momentum_body_com=rotate(inertia.angular_momentum_body_com),
            inertia_tensor_body_com=InertiaTensor.from_matrix(_transform_tensor(R, REFERENCE_INERTIA.to_tuple())),
        )
        before = convert_body_motion_to_dynamics_state(replace(motion, pose=pose), inertia)
        after = convert_body_motion_to_dynamics_state(replace(motion, pose=rotated_pose, velocity=rotated_velocity),
                                                      rotated_inertia)
        self.assert_vector_close(after.com_position_world, rotate(before.com_position_world))
        self.assert_vector_close(after.com_velocity_world, rotate(before.com_velocity_world))
        self.assert_vector_close(after.linear_momentum_world, rotate(before.linear_momentum_world))
        self.assert_vector_close(after.angular_momentum_about_com_world, rotate(before.angular_momentum_about_com_world))
        self.assert_tensor_close(after.inertia_tensor_body.to_matrix(), before.inertia_tensor_body.to_matrix())
        self.assert_rotation_equivalent(after.orientation_quat_world, Q)
        self.assertEqual(after.mass, before.mass)
        self.assertEqual(after.timestamp, before.timestamp)

    def test_t07_root_com_and_commanded_velocity_are_distinct(self):
        motion = self.standing_motion
        com_velocity = (0.25, -0.75, 1.25)
        root_velocity = (-1.0, 0.5, 0.0)
        commanded_velocity = (9.0, 2.0, -3.0)
        pose = replace(motion.pose, root_position=(10.0, 20.0, 30.0), commanded_velocity=commanded_velocity)
        velocity = replace(motion.velocity, root_linear_velocity=root_velocity,
                           com_linear_velocity=com_velocity, commanded_velocity=commanded_velocity)
        inertia = replace(self.standing_inertia, com_linear_velocity=com_velocity)
        state = convert_body_motion_to_dynamics_state(replace(motion, pose=pose, velocity=velocity), inertia)
        self.assertEqual(state.com_position_world, inertia.com_world)
        self.assertNotEqual(state.com_position_world, pose.root_position)
        self.assertEqual(state.com_velocity_world, com_velocity)
        self.assertNotEqual(state.com_velocity_world, root_velocity)
        self.assertNotEqual(state.com_velocity_world, commanded_velocity)

    def test_t08_real_independent_arm_spin_orbital_and_total_angular_momentum(self):
        self.assertEqual(self.moving_bone_count, 19)
        _, motion, inertia, wbc_result = self.moving_frame
        self.assertTrue(wbc_result.success)
        self.assertFalse(wbc_result.has_rom_violation)
        self.assertTrue(wbc_result.end_effectors["hand_L"].enabled)
        self.assertTrue(wbc_result.end_effectors["hand_L"].is_reachable)
        self.assertGreater(math.hypot(*motion.velocity.segment_angular_velocities["upper_arm_L"]), 0.0)
        spin = tuple(math.fsum(seg.spin_angular_momentum[i] for seg in inertia.segments.values()) for i in range(3))
        orbital = tuple(math.fsum(seg.orbital_angular_momentum[i] for seg in inertia.segments.values()) for i in range(3))
        self.assertGreater(math.hypot(*spin), 0.0)
        self.assertGreater(math.hypot(*orbital), 0.0)
        self.assertGreater(inertia.angular_momentum_magnitude, 0.0)
        self.assert_vector_close(inertia.spin_angular_momentum_total, spin)
        self.assert_vector_close(inertia.orbital_angular_momentum_total, orbital)
        state = convert_body_motion_to_dynamics_state(motion, inertia)
        self.assertEqual(state.angular_momentum_about_com_world, inertia.angular_momentum_body_com)
        self.assert_vector_close(state.angular_momentum_about_com_world, tuple(a + b for a, b in zip(spin, orbital)))

    def test_t09_equivalent_angular_velocity_is_not_root_angular_velocity(self):
        motion = self.standing_motion
        velocity = replace(motion.velocity, root_angular_velocity=(0.5, -0.25, 0.125))
        pose = replace(motion.pose, root_orientation_quat=(1.0, 0.0, 0.0, 0.0))
        inertia = replace(self.standing_inertia, inertia_tensor_body_com=InertiaTensor(4.0, 5.0, 6.0),
                          angular_momentum_body_com=(4.0, 10.0, -18.0))
        state = convert_body_motion_to_dynamics_state(replace(motion, pose=pose, velocity=velocity), inertia)
        self.assert_vector_close(state.angular_velocity_world, (1.0, 2.0, -3.0), tolerance=1e-9)
        self.assertNotEqual(state.angular_velocity_world, velocity.root_angular_velocity)

    def test_t10_snapshot_contract_rejects_mismatches(self):
        motion, inertia = self.standing_motion, self.standing_inertia
        pose, velocity = motion.pose, motion.velocity
        segment_id, segment = next(iter(inertia.segments.items()))
        segments = dict(inertia.segments)
        smaller = {key: value for key, value in segments.items() if key != segment_id}
        cases = (
            ("timestamp gap", motion, replace(inertia, time_sec=pose.time_sec + 2e-9)),
            ("pairwise timestamp gap", replace(motion, velocity=replace(velocity, time_sec=pose.time_sec - 7e-10)),
             replace(inertia, time_sec=pose.time_sec + 7e-10)),
            ("negative timestamp", replace(motion, pose=replace(pose, time_sec=-1.0)), inertia),
            ("small dt", replace(motion, velocity=replace(velocity, dt=1e-9)), inertia),
            ("frame mismatch", motion, replace(inertia, frame=pose.frame + 1)),
            ("missing frame", motion, replace(inertia, frame=None)),
            ("reference frame", motion, replace(inertia, reference_frame="BODY")),
            ("reference point", motion, replace(inertia, reference_point="ROOT")),
            ("zero mass", motion, replace(inertia, total_mass_kg=0.0)),
            ("mass sum", motion, replace(inertia, total_mass_kg=inertia.total_mass_kg * 1.001)),
            ("zero segment mass", motion, replace(inertia, segments={**segments, segment_id: replace(segment, mass_kg=0.0)})),
            ("segment missing", motion, replace(inertia, segments=smaller)),
            ("pose segment missing", replace(motion, pose=replace(pose, segment_positions={})), inertia),
            ("pose orientation missing", replace(motion, pose=replace(pose, segment_orientations={})), inertia),
            ("velocity segment missing", replace(motion, velocity=replace(velocity, segment_linear_velocities={})), inertia),
            ("angular velocity segment missing", replace(motion, velocity=replace(velocity, segment_angular_velocities={})), inertia),
            ("CoM mismatch", motion, replace(inertia, com_world=(inertia.com_world[0] + 0.01, *inertia.com_world[1:]))),
            ("CoM velocity mismatch", motion, replace(inertia, com_linear_velocity=(9.0, 8.0, 7.0))),
        )
        for label, left, right in cases:
            with self.subTest(label=label):
                before = deepcopy((left, right))
                with self.assertRaises(ValueError) as error:
                    convert_body_motion_to_dynamics_state(left, right)
                self.assertTrue(str(error.exception))
                self.assertEqual((left, right), before)

    def test_t11_rejects_illegal_types_nonfinite_values_quaternions_and_tensors(self):
        motion, inertia = self.standing_motion, self.standing_inertia
        pose, velocity = motion.pose, motion.velocity
        cases = (
            (TypeError, None, inertia),
            (TypeError, motion, None),
            (TypeError, replace(motion, pose=None), inertia),
            (TypeError, replace(motion, velocity=None), inertia),
            (TypeError, motion, replace(inertia, inertia_tensor_body_com=None)),
            (TypeError, replace(motion, pose=replace(pose, frame=True)), inertia),
            (TypeError, motion, replace(inertia, total_mass_kg="70")),
            (TypeError, motion, replace(inertia, com_world="123")),
            (TypeError, motion, replace(inertia, com_world=(True, 1.0, 2.0))),
            (TypeError, motion, replace(inertia, angular_momentum_body_com=(0.0, None, 0.0))),
            (TypeError, replace(motion, pose=replace(pose, root_orientation_quat=(1.0, "0", 0.0, 0.0))), inertia),
            (ValueError, replace(motion, velocity=replace(velocity, dt=math.inf)), inertia),
            (ValueError, motion, replace(inertia, time_sec=math.nan)),
            (ValueError, motion, replace(inertia, angular_momentum_body_com=(0.0, math.inf, 0.0))),
            (ValueError, motion, replace(inertia, com_linear_velocity=(0.0, 1.0))),
            (ValueError, replace(motion, pose=replace(pose, root_orientation_quat=(1.0, 0.0, 0.0))), inertia),
            (ValueError, replace(motion, pose=replace(pose, root_orientation_quat=(0.0, 0.0, 0.0, 0.0))), inertia),
            (ValueError, replace(motion, pose=replace(pose, root_orientation_quat=(1.1, 0.0, 0.0, 0.0))), inertia),
            (ValueError, replace(motion, pose=replace(pose, root_orientation_quat=(math.inf, 0.0, 0.0, 0.0))), inertia),
            (ValueError, motion, replace(inertia, inertia_tensor_body_com=InertiaTensor(math.inf, 5.0, 6.0))),
            (ValueError, motion, replace(inertia, inertia_tensor_body_com=InertiaTensor(-4.0, 5.0, 6.0))),
            (ValueError, motion, replace(inertia, inertia_tensor_body_com=InertiaTensor(2.0, 2.0, 5.0))),
            (ValueError, motion, replace(inertia, inertia_tensor_body_com=InertiaTensor(1e-4, 1e-4, 1e-4))),
        )
        for index, (expected_error, left, right) in enumerate(cases, 1):
            with self.subTest(case=index, expected=expected_error.__name__):
                before = repr((left, right))
                with self.assertRaises(expected_error) as error:
                    convert_body_motion_to_dynamics_state(left, right)
                self.assertTrue(str(error.exception))
                self.assertEqual(repr((left, right)), before)

    def test_t12_repeatability_immutability_and_no_scene_side_effects(self):
        tracker, motion, inertia, _ = self.moving_frame
        input_before = deepcopy((motion, inertia))
        tracker_identity = (id(tracker._prev_snapshot), id(tracker._prev_velocity), id(tracker._history))
        track_before = deepcopy((tracker._prev_snapshot, tracker._prev_velocity, tracker._history))
        scene_before = _scene_values()
        self.assertTrue(any(curve[2] for _, curves in scene_before[-1] for curve in curves))

        outputs = [convert_body_motion_to_dynamics_state(motion, inertia) for _ in range(100)]
        output = outputs[0]
        self.assertTrue(all(value == output for value in outputs))
        for value in (output.com_position_world, output.com_velocity_world,
                      output.angular_momentum_about_com_world, output.orientation_quat_world):
            self.assertIsInstance(value, tuple)
        with self.assertRaises(FrozenInstanceError):
            output.mass = 1.0
        with self.assertRaises(FrozenInstanceError):
            output.inertia_tensor_body.ixx = 1.0
        self.assertEqual((motion, inertia), input_before)
        self.assertEqual((tracker._prev_snapshot, tracker._prev_velocity, tracker._history), track_before)
        self.assertEqual((id(tracker._prev_snapshot), id(tracker._prev_velocity), id(tracker._history)), tracker_identity)
        self.assertEqual(_scene_values(), scene_before)
        self.assertEqual(_sha256_file(PLAYGROUND_BLEND), self.source_hash)


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1:])
    unittest.main(argv=argv, verbosity=2)
