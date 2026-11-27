"""TASK 12-D Group C: Cross-Module Telemetry Ownership & 10-C Retirement Verification (C01-C16).

Run via real Blender 5.1.1:
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P docs/evidence/12/unified_verification/verify_telemetry_ownership.py
"""

from __future__ import annotations

import datetime
import json
import math
import os
import sys
import traceback
from dataclasses import replace as dc_replace
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

import bpy
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import src.motion.body_inertia as bi_mod
import src.motion.body_kinematics as bk_mod
import src.motion.kinematic_bridge as kb_mod
import src.motion.rigid_link as rl_mod
import src.motion.whole_body_controller as wbc_mod
from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.body_inertia import (
    DEFAULT_15_SEGMENT_INERTIA_MODEL,
    BodyInertiaModel,
    SegmentGeometrySpec,
    compute_whole_body_inertia,
)
from src.motion.body_kinematics import (
    BodyKinematicsTracker,
    sample_body_pose_from_controller_result,
    sample_body_pose_snapshot,
)
from src.motion.contact_model import ContactLifecycle, ContactType, EnvironmentalSurface
from src.motion.framework import (
    EnvironmentQuery,
    MotionMode,
    MotionPlanner,
    StartStopWalkAction,
    SurfaceQueryResult,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.motion.rigid_link import BodyMassDistribution, DEMPSTER_WINTER_15_SEGMENT_MODEL, RigidSegmentSpec
from src.motion.run_cycle import RunAction
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.upper_limb_trajectory import UpperLimbSegment
from src.motion.whole_body_controller import WholeBodyControlTargets, WholeBodyController
from src.rig.arm_ik import MAX_ARM_REACH, get_arm_ik_state, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, setup_leg_ik
from src.rig.pose import reset_pose

OUTPUT_JSON = os.path.join(THIS_DIR, "telemetry_results.json")


def _clean_scene(y_root: float = -8.0, env: Optional[EnvironmentQuery] = None, surfaces=None) -> Tuple[bpy.types.Object, bpy.types.Object, KinematicBridgeExecutor]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    root = arm.parent or bpy.data.objects.get("CharacterRoot")
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    if root is not None:
        root.location = Vector((0.0, y_root, 0.0))
    bpy.context.view_layer.update()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root, environment=env, surfaces=surfaces)
    return arm, root, bridge


def _base_pose(frame: int = 1, t: float = 0.0, y_root: float = -8.0, **kw) -> KinematicPlannedPose:
    return KinematicPlannedPose(
        frame=frame,
        time_seconds=t,
        root_position=(0.0, y_root, 0.0),
        foot_L=kw.get("foot_L", PlannedFootTarget((-HIP_X_OFFSET, y_root, ANKLE_REST_Z), is_locked=True)),
        foot_R=kw.get("foot_R", PlannedFootTarget((HIP_X_OFFSET, y_root, ANKLE_REST_Z), is_locked=True)),
        hand_L=kw.get("hand_L", PlannedHandTarget((0.0, 0.0, 0.0), enabled=False)),
        hand_R=kw.get("hand_R", PlannedHandTarget((0.0, 0.0, 0.0), enabled=False)),
        spine_rotation_deg=kw.get("spine_rotation_deg", (0.0, 0.0, 0.0)),
    )


def test_c01() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    p = _base_pose(
        frame=1,
        t=0.0,
        spine_rotation_deg=(85.0, 0.0, 0.0),
        hand_L=PlannedHandTarget((-0.25, -7.70, 1.15), rotation_deg=(12.0, 8.0, -5.0), enabled=True, weight=1.0),
    )
    res = bridge.execute_frame(p, keyframe=False, enforce_rom_clamping=True)
    assert res.success is False
    for eff_id, err in res.tracking_errors.items():
        fb = res.wbc_result.end_effectors[eff_id]
        assert fb.enabled and math.isclose(err, fb.position_error_m, abs_tol=1e-9)
    assert res.rom_violations == res.wbc_result.rom_validation.violations
    for uc in res.wbc_result.unmet_constraints:
        assert uc in res.unmet_constraints
    return {"tracking_errors": {k: round(v, 6) for k, v in res.tracking_errors.items()}}


def test_c02() -> Dict[str, Any]:
    assert not hasattr(kb_mod, "_reconcile_post_rom_feedback"), "Deprecated _reconcile_post_rom_feedback still present!"
    src = open(os.path.join(REPO_ROOT, "src", "motion", "kinematic_bridge.py"), "r", encoding="utf-8").read()
    assert src.count("_reconcile_post_rom_feedback") == 0
    return {"_reconcile_post_rom_feedback_removed": True}


def test_c03() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    counts = {"wbc": 0, "body_kinematics": 0, "body_inertia": 0}
    orig_wbc_com = wbc_mod.compute_whole_body_com
    orig_bk_com = bk_mod.compute_whole_body_com
    orig_bi_com = bi_mod.compute_whole_body_com

    def c_wbc(*a, **kw):
        counts["wbc"] += 1
        return orig_wbc_com(*a, **kw)

    def c_bk(*a, **kw):
        counts["body_kinematics"] += 1
        return orig_bk_com(*a, **kw)

    def c_bi(*a, **kw):
        counts["body_inertia"] += 1
        return orig_bi_com(*a, **kw)

    with patch.object(wbc_mod, "compute_whole_body_com", side_effect=c_wbc), patch.object(
        bk_mod, "compute_whole_body_com", side_effect=c_bk
    ), patch.object(bi_mod, "compute_whole_body_com", side_effect=c_bi):
        res = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert res.success is True
    assert counts == {"wbc": 1, "body_kinematics": 0, "body_inertia": 0}, f"CoM called more than once: {counts}"
    return counts


def test_c04() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    res = bridge.execute_frame(
        _base_pose(1, 0.0, hand_L=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0)),
        keyframe=False,
    )
    assert res.success
    c_wbc = tuple(float(v) for v in res.wbc_result.com_result.com_world)
    c_bridge = tuple(float(v) for v in res.com_world)
    c_snap = tuple(float(v) for v in bridge.kinematics_tracker._history[-1].com_world)
    c_iner = tuple(float(v) for v in res.inertia_state.com_world)
    c_ms = tuple(float(v) for v in res.motion_state.params["com_world"])
    for cand in (c_bridge, c_snap, c_iner, c_ms):
        assert math.dist(c_wbc, cand) < 1e-9, f"CoM mismatch: {c_wbc} != {cand}"
    return {"com_world": tuple(round(v, 6) for v in c_wbc)}


def test_c05() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    res = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert res.success
    wbc_segs = res.wbc_result.com_result.segments
    snap_segs = bridge.kinematics_tracker._history[-1].pose.segment_positions
    iner_segs = res.inertia_state.segments
    assert set(wbc_segs.keys()) == set(snap_segs.keys()) == set(iner_segs.keys())
    for sid, ws in wbc_segs.items():
        assert math.isclose(ws.mass_kg, iner_segs[sid].mass_kg, abs_tol=1e-9)
        assert math.dist(tuple(ws.world_com), snap_segs[sid]) < 1e-9
        assert math.dist(tuple(ws.world_com), iner_segs[sid].world_com) < 1e-9
    return {"verified_segments": len(wbc_segs)}


def _clone_dist_with_meta(base: BodyMassDistribution, name: str) -> BodyMassDistribution:
    segs = tuple(
        RigidSegmentSpec(
            segment_id=s.segment_id,
            bone_name=s.bone_name,
            mass_ratio=s.mass_ratio,
            nominal_length=s.nominal_length,
            local_com_fraction=s.local_com_fraction,
            local_com_offset=tuple(s.local_com_offset),
            description=f"{s.description} [{name}]",
        )
        for s in base.segments
    )
    return BodyMassDistribution(model_name=name, source=f"Custom {name}", total_mass_kg=base.total_mass_kg, segments=segs)


def test_c06() -> Dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    root = arm.parent or bpy.data.objects.get("CharacterRoot")
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    if root is not None:
        root.location = Vector((0.0, -8.0, 0.0))
    bpy.context.view_layer.update()

    base = DEMPSTER_WINTER_15_SEGMENT_MODEL.with_total_mass(75.0)
    d_wbc = _clone_dist_with_meta(base, "WBC_75_Alpha")
    d_trk = _clone_dist_with_meta(base, "Tracker_75_Beta")
    d_inr = _clone_dist_with_meta(base, "Inertia_75_Gamma")

    wbc = WholeBodyController(armature_obj=arm, root_obj=root, mass_distribution=d_wbc, config=cfg)
    trk = BodyKinematicsTracker(armature_obj=arm, root_obj=root, mass_distribution=d_trk, config=cfg)
    inr = BodyInertiaModel("CustomInert_75", "Test", mass_distribution=d_inr, geometries=DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries)
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root, controller=wbc, kinematics_tracker=trk, inertia_model=inr)
    res = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert res.success is True
    assert math.isclose(res.wbc_result.com_result.total_mass_kg, 75.0, abs_tol=1e-9)
    assert math.isclose(res.inertia_state.total_mass_kg, 75.0, abs_tol=1e-9)
    return {"custom_total_mass_kg": res.inertia_state.total_mass_kg}


def test_c07() -> Dict[str, Any]:
    base = DEMPSTER_WINTER_15_SEGMENT_MODEL
    # Build 6 physical mismatch variants (same model_name to ensure we are NOT just checking names)
    def replace_seg(target_id: str, **fields) -> BodyMassDistribution:
        segs = tuple(dc_replace(s, **fields) if s.segment_id == target_id else s for s in base.segments)
        return BodyMassDistribution(model_name=base.model_name, source=base.source, total_mass_kg=base.total_mass_kg, segments=segs)

    bad_total = base.with_total_mass(80.0)
    segs_id_renamed = tuple(
        dc_replace(s, segment_id="pelvis_renamed") if s.segment_id == "pelvis" else s for s in base.segments
    )
    bad_seg_id = BodyMassDistribution(model_name=base.model_name, source=base.source, total_mass_kg=base.total_mass_kg, segments=segs_id_renamed)
    bad_bone = replace_seg("pelvis", bone_name="spine")
    bad_ratio = base.with_overrides({"head": 0.12}, new_model_name=base.model_name, normalize=True)
    bad_frac = replace_seg("head", local_com_fraction=0.65)
    bad_offset = replace_seg("foot_L", local_com_offset=(0.0, 0.0, 0.02))

    variants = [
        ("total_mass", bad_total),
        ("segment_id_map", bad_seg_id),
        ("bone_name", bad_bone),
        ("mass_ratio", bad_ratio),
        ("local_com_fraction", bad_frac),
        ("local_com_offset", bad_offset),
    ]
    rejected = {}
    for label, bad_dist in variants:
        arm, root, bridge = _clean_scene()
        bridge.inertia_model = BodyInertiaModel("MismatchModel", "Test", mass_distribution=bad_dist, geometries=DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries)
        wbc_calls = [0]
        orig_wbc = bridge.controller.execute_frame

        def spy_wbc(*a, **kw):
            wbc_calls[0] += 1
            return orig_wbc(*a, **kw)

        with patch.object(bridge.controller, "execute_frame", side_effect=spy_wbc):
            try:
                bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
                raise AssertionError(f"C07 variant {label} was not rejected")
            except ValueError:
                pass
        assert wbc_calls[0] == 0, f"C07 {label}: WBC was called before rejection!"
        rejected[label] = True
    return rejected


def test_c08() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    # Make shin.L bone unusually elongated? Or use custom geometry on forearm.L and verify actual bone pb.length is used vs nominal_length!
    pb_shin = arm.pose.bones["shin.L"]
    actual_len = float(pb_shin.length)
    # Create custom geometry where nominal_length (0.99m) deliberately differs from actual pb.length (~0.40m)
    custom_geom = SegmentGeometrySpec(
        segment_id="shin_L",
        shape_type="cylinder",
        radius_x=0.06,
        nominal_length=0.99,
    )
    custom_inertia = DEFAULT_15_SEGMENT_INERTIA_MODEL.with_overrides({"shin_L": custom_geom})
    bridge.inertia_model = custom_inertia
    res = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert res.success
    mass_kg = res.wbc_result.com_result.segments["shin_L"].mass_kg
    expected_local = custom_geom.compute_local_tensor(mass_kg=mass_kg, actual_length=actual_len)
    nominal_local = custom_geom.compute_local_tensor(mass_kg=mass_kg, actual_length=0.99)
    actual_local = res.inertia_state.segments["shin_L"].local_inertia
    assert abs(actual_local.ixx - expected_local.ixx) < 1e-8
    assert abs(actual_local.ixx - nominal_local.ixx) > 0.01
    return {"actual_len_m": round(actual_len, 4), "actual_ixx": round(actual_local.ixx, 6), "nominal_ixx": round(nominal_local.ixx, 6)}


def test_c09() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    t = 0.125
    res = bridge.execute_frame(_base_pose(4, t), keyframe=False, dt=0.05)
    assert res.success
    hist = bridge.kinematics_tracker._history[-1]
    assert res.frame == 4 and res.motion_state.frame == 4 and hist.frame == 4 and res.inertia_state.frame == 4
    assert math.isclose(res.motion_state.time_sec, t, abs_tol=1e-9)
    assert math.isclose(hist.time_sec, t, abs_tol=1e-9)
    assert math.isclose(hist.velocity.time_sec, t, abs_tol=1e-9)
    assert math.isclose(res.inertia_state.time_sec, t, abs_tol=1e-9)
    return {"frame": res.frame, "time_sec": t}


def test_c10() -> Dict[str, Any]:
    class AirGapEnv(EnvironmentQuery):
        def query_ground_support_at(self, x: float, y: float, **kwargs) -> SurfaceQueryResult:
            return SurfaceQueryResult(
                surface_id="sunken_floor",
                surface_type="horizontal_ground",
                contact_point_world=(x, y, -0.05),  # 50mm air gap under foot sole at Z=0!
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=0.05,
                friction_coeff=0.65,
                allows_regular_support=True,
                success=True,
            )

    arm, root, bridge = _clean_scene(env=AirGapEnv())
    res = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert res.success is False
    # FootIK.L/R controllers ARE locked at Rig level, yet ContactModel failed geometric compliance!
    assert bool(bpy.data.objects["FootIK.L"]["is_locked"]) is True
    assert "foot_L" not in res.multi_contact.effective_contacts
    assert res.motion_state.contacts["foot_L"].is_locked is False
    assert len(bridge.kinematics_tracker._history) == 0  # Also uncommitted!
    # Also inspect raw snapshot via sample_body_pose_snapshot with contacts_override derived from effective_contacts:
    assert res.motion_state.params["active_contact_count"] == 0
    return {"foot_L_effective_in_ms": res.motion_state.contacts["foot_L"].is_locked}


def test_c11() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    # Frame 1: Double stance (both effective)
    r1 = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    # Frame 2: Left stance, Right swing
    r2 = bridge.execute_frame(
        _base_pose(2, 1.0 / 24.0, foot_R=PlannedFootTarget((HIP_X_OFFSET, -7.95, ANKLE_REST_Z + 0.06), is_locked=False, contact_intent=False)),
        keyframe=False,
    )
    assert r1.success and r2.success
    s1 = bridge.kinematics_tracker._history[0].pose.contacts
    s2 = bridge.kinematics_tracker._history[1].pose.contacts
    assert s1["foot_L"] is True and s1["foot_R"] is True
    assert s2["foot_L"] is True and s2["foot_R"] is False
    assert r2.motion_state.contacts["foot_L"].is_locked is True and r2.motion_state.contacts["foot_R"].is_locked is False
    return {"s1": s1, "s2": s2}


def test_c12() -> Dict[str, Any]:
    # Frame A: free hand IK; Frame B: candidate hand contact; Frame C: established compliant hand contact
    box_surf = EnvironmentalSurface("vault_box", "box_top", center_world=(-0.25, -7.75, 1.25), normal_world=(0.0, 0.0, 1.0))
    arm, root, bridge = _clean_scene(surfaces=[box_surf])
    # A: Free IK
    r_free = bridge.execute_frame(
        _base_pose(1, 0.0, hand_L=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0, contact_intent=False, is_locked=False)),
        keyframe=False,
    )
    assert r_free.success
    assert r_free.multi_contact.contacts["hand_L"].lifecycle == ContactLifecycle.RELEASED
    assert bridge.kinematics_tracker._history[-1].pose.contacts["hand_L"] is False
    assert r_free.motion_state.contacts["hand_L"].is_locked is False

    # B: Candidate contact (dist > 0.015m with weight=0.0 so hand stays at rest far from target)
    r_cand = bridge.execute_frame(
        _base_pose(2, 1.0 / 24.0, hand_L=PlannedHandTarget((-0.25, -7.60, 1.25), enabled=True, weight=0.0, contact_intent=True, is_locked=False, surface_id="vault_box")),
        keyframe=False,
    )
    assert r_cand.success
    assert r_cand.multi_contact.contacts["hand_L"].lifecycle == ContactLifecycle.CANDIDATE
    assert bridge.kinematics_tracker._history[-1].pose.contacts["hand_L"] is False
    assert r_cand.motion_state.contacts["hand_L"].is_locked is False

    # C: Established compliant contact (palm anchor is at local (0, 0.050, -0.015) from wrist, align target/surface!)
    # Run once with free hand IK to get exact palm anchor at reached pose, then set matching vault_box center!
    r_reach = bridge.execute_frame(
        _base_pose(3, 2.0 / 24.0, hand_L=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0, contact_intent=False)),
        keyframe=False,
    )
    assert r_reach.success
    p_hand = arm.pose.bones["hand.L"]
    palm_world = (arm.matrix_world @ p_hand.matrix) @ Vector((0.0, 0.050, -0.015))
    palm_xyz = (float(palm_world.x), float(palm_world.y), float(palm_world.z))
    exact_surf = EnvironmentalSurface("vault_box", "box_top", center_world=palm_xyz, normal_world=(0.0, 0.0, 1.0))
    bridge.surfaces = [exact_surf]
    r_est = bridge.execute_frame(
        _base_pose(4, 3.0 / 24.0, hand_L=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0, contact_intent=True, is_locked=True, surface_id="vault_box", contact_type=ContactType.UNILATERAL)),
        keyframe=False,
    )
    assert r_est.success, f"Established hand contact failed: {r_est.unmet_constraints}"
    assert "hand_L" in r_est.multi_contact.effective_contacts
    assert bridge.kinematics_tracker._history[-1].pose.contacts["hand_L"] is True
    assert r_est.motion_state.contacts["hand_L"].is_locked is True
    return {"free": False, "candidate": False, "established": True}


def test_c13() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    res = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert res.success
    eff_keys = set(res.multi_contact.effective_contacts.keys())
    snap_contacts = bridge.kinematics_tracker._history[-1].pose.contacts
    ms_contacts = res.motion_state.contacts
    assert set(res.motion_state.params["supporting_limbs"]) == eff_keys
    for limb in ("foot_L", "foot_R", "hand_L", "hand_R"):
        expected = limb in eff_keys
        assert snap_contacts[limb] is expected
        assert ms_contacts[limb].is_locked is expected
    return {"effective_limbs": sorted(eff_keys)}


def test_c14() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    wbc_res = bridge.controller.execute_frame(WholeBodyControlTargets())
    snap_standalone = sample_body_pose_snapshot(arm, root, time_sec=0.0, frame=1)
    snap_ctrl = sample_body_pose_from_controller_result(wbc_res, time_sec=0.0, frame=1, armature_obj=arm, root_obj=root)
    assert snap_standalone.com_world == tuple(round(v, 12) for v in snap_standalone.com_world) or math.isfinite(snap_standalone.com_world[2])
    assert snap_ctrl.source == "whole_body_controller"
    trk = BodyKinematicsTracker(armature_obj=arm, root_obj=root)
    bms = trk.sample_and_update(time_sec=0.0, frame=1)
    assert len(trk._history) == 1
    iner = compute_whole_body_inertia(arm, velocity_state=bms.velocity, time_sec=0.0, frame=1)
    assert math.isclose(iner.total_mass_kg, 70.0, abs_tol=1e-9)
    return {"legacy_standalone_apis_intact": True}


def test_c15() -> Dict[str, Any]:
    cfg = PipelineConfig()
    actions = [
        ("start_stop_walk", lambda: StartStopWalkAction()),
        ("terrain_walk", lambda: TerrainWalkAction(
            route=TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -7.2, 0.0), nominal_stride_m=0.35),
        )),
        ("run", lambda: RunAction(cycles=1)),
        ("sprint_start", lambda: SprintStartAction()),
        ("sprint_brake", lambda: SprintBrakeAction()),
    ]
    executed = {}
    for name, fn in actions:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_character(cfg)
        arm = build_rig(cfg)
        bind_character_to_rig(arm)
        reset_pose(arm)
        setup_leg_ik(arm)
        setup_arm_ik(arm, initial_influence=0.0)
        bpy.context.view_layer.update()
        planner = MotionPlanner(cfg, armature_obj=arm, environment=EnvironmentQuery(ground_z=0.0))
        planner.add_action(fn())
        init_st = create_initial_motion_state(cfg, start_frame=1)
        if name == "sprint_brake":
            init_st = init_st.clone_with(mode=MotionMode.SPRINT, velocity=(0.0, 2.0, 0.0))
        res = planner.execute(initial_state=init_st)
        executed[name] = len(res["states"])
    return {"actions_frames": executed}


def test_c16() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    r1 = bridge.execute_frame(_base_pose(1, 0.0), keyframe=False)
    assert r1.success
    prev_snap = bridge.kinematics_tracker._prev_snapshot
    prev_mc = bridge.last_multi_contact
    r2 = bridge.execute_frame(_base_pose(2, 1.0 / 24.0, spine_rotation_deg=(88.0, 0.0, 0.0)), keyframe=False)
    assert r2.success is False
    assert r2.motion_state is not None and r2.multi_contact is not None
    assert bridge.kinematics_tracker._prev_snapshot is prev_snap
    assert bridge.last_multi_contact is prev_mc
    assert len(bridge.kinematics_tracker._history) == 1
    return {"diagnostics_isolated_from_committed_cache": True}


def test_10c_retirement() -> Dict[str, Any]:
    """Section 9: Verify historical 10-C C4-T07/T08/T09 contracts on current WBC/Bridge."""
    arm, root, bridge = _clean_scene()
    # C4-T07: Pre-ROM vs Post-ROM sync on Bridge when enforce_rom_clamping=True
    p_rom = _base_pose(
        1,
        0.0,
        spine_rotation_deg=(85.0, 0.0, 0.0),
        hand_L=PlannedHandTarget((-0.25, -7.70, 1.15), rotation_deg=(10.0, 5.0, 0.0), enabled=True, weight=1.0),
    )
    res_rom = bridge.execute_frame(p_rom, keyframe=False, enforce_rom_clamping=True)
    assert res_rom.success is False
    assert any(u.category == "ROM_VIOLATION" for u in res_rom.unmet_constraints)
    fb_hl = res_rom.wbc_result.end_effectors["hand_L"]
    actual_w = tuple(float(v) for v in get_arm_ik_state(arm, "L")["wrist_world"])
    assert math.dist(fb_hl.actual_world_xyz, actual_w) < 1e-5
    # C4-T08: Unreachable + ROM invalid -> both REACHABILITY and ROM_VIOLATION retained
    st_r = get_arm_ik_state(arm, "R")
    far_target = (float(st_r["shoulder_world"].x), float(st_r["shoulder_world"].y) + MAX_ARM_REACH + 0.3, float(st_r["shoulder_world"].z))
    p_both = _base_pose(
        2,
        1.0 / 24.0,
        spine_rotation_deg=(85.0, 0.0, 0.0),
        hand_R=PlannedHandTarget(far_target, enabled=True, weight=1.0, clamp_reach=False),
    )
    res_both = bridge.execute_frame(p_both, keyframe=False, enforce_rom_clamping=True)
    cats = {u.category for u in res_both.unmet_constraints}
    assert "ROM_VIOLATION" in cats and "REACHABILITY" in cats
    # C4-T09: Non-blocking propagation & no deleted reconciler
    assert not hasattr(kb_mod, "_reconcile_post_rom_feedback")
    return {"c4_t07_t08_t09_reverified_on_production": True}


TESTS: List[Tuple[str, Callable[[], Dict[str, Any]]]] = [
    ("C01", test_c01),
    ("C02", test_c02),
    ("C03", test_c03),
    ("C04", test_c04),
    ("C05", test_c05),
    ("C06", test_c06),
    ("C07", test_c07),
    ("C08", test_c08),
    ("C09", test_c09),
    ("C10", test_c10),
    ("C11", test_c11),
    ("C12", test_c12),
    ("C13", test_c13),
    ("C14", test_c14),
    ("C15", test_c15),
    ("C16", test_c16),
    ("10C_RETIREMENT_C4_T07_T09", test_10c_retirement),
]


def main() -> int:
    results: Dict[str, Any] = {}
    all_ok = True
    for tid, fn in TESTS:
        try:
            detail = fn()
            results[tid] = {"status": "PASSED", "detail": detail}
            print(f"[PASS] {tid}: {detail}")
        except Exception as exc:
            all_ok = False
            results[tid] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
            print(f"[FAIL] {tid}: {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc()
            break

    payload = {
        "group": "Group C — Cross-Module Telemetry Ownership & 10-C Retirement (C01-C16)",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "passed": all_ok,
        "total": len(TESTS),
        "passed_count": sum(1 for v in results.values() if v["status"] == "PASSED"),
        "results": results,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
