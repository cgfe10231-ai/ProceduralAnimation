"""Reopen character_sprint_start_prototype.blend and verify Task 6C:
velocity profile, variable gait (cadence/stance/flight/step length), stance lock drift & landing error,
flight clearance, penetration, knee direction, IK reach, pose continuity, crouch/lean posture,
non-zero final state via MotionPlanner (offset start), and gait trend checks."""

import math
import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.motion.framework import MotionMode, MotionPlanner, create_initial_motion_state
from src.motion.sprint_start import SprintStartAction, build_sprint_schedule
from src.rig.ik import IK_TARGET_NAMES, MAX_LEG_REACH, get_leg_ik_state


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 6C SPRINT START REOPEN VERIFICATION ===")
    config = PipelineConfig()
    scene = bpy.context.scene
    sx, sy, sz = config.character_path_points[0]
    total = config.sprint_total_frames
    prep = config.sprint_prep_frames
    accel = config.sprint_accel_frames
    vmax = config.sprint_target_speed
    fps = float(config.fps)

    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != total:
        _fail(f"Bad timeline: {scene.render.fps} {scene.frame_start}..{scene.frame_end}")
    arm = bpy.data.objects.get("CharacterArmature")
    root = bpy.data.objects.get("CharacterRoot")
    ik = {s: bpy.data.objects.get(IK_TARGET_NAMES[s]) for s in "LR"}
    if arm is None or root is None or None in ik.values():
        _fail("Missing rig objects")
    for n in ("CharacterRoot", "CharacterArmature", "FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R"):
        o = bpy.data.objects.get(n)
        if o is None or o.animation_data is None or o.animation_data.action is None:
            _fail(f"{n} missing Action")
    print("Verified saved Actions on root/armature/IK/pole objects")

    steps = build_sprint_schedule(config, sy)

    def stance_y(j):
        return sy if j <= 0 else steps[j]["stance_y"]

    root_y, pelvis_z, pitch, arm_l = [], [], [], []
    ref = {}
    max_drift = {"L": 0.0, "R": 0.0}
    max_landing = 0.0
    min_z = 999.0
    flight_min_z = 999.0
    min_knee = 999.0
    max_dist = 0.0
    unreachable = 0
    airborne_per_step = {}
    steady_pelvis = []

    for frame in range(1, total + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        tau = frame - 1
        rp = root.matrix_world.translation
        if abs(rp.x - sx) > 1e-5 or abs(rp.z - sz) > 1e-5:
            _fail(f"Root X/Z drift frame {frame}")
        root_y.append(rp.y)
        pb_p, pb_s = arm.pose.bones["pelvis"], arm.pose.bones["spine"]
        hz = (arm.matrix_world @ pb_p.head).z
        pelvis_z.append(hz)
        pitch.append(-math.degrees(pb_p.rotation_euler.x + pb_s.rotation_euler.x))
        arm_l.append(math.degrees(arm.pose.bones["upper_arm.L"].rotation_euler.x))

        st = {s: get_leg_ik_state(arm, s) for s in "LR"}
        lock = {s: bool(ik[s].get("is_locked", False)) for s in "LR"}
        for s in "LR":
            d = (st[s]["target_world"] - st[s]["hip_world"]).length
            max_dist = max(max_dist, d)
            if d > MAX_LEG_REACH + 1e-4:
                unreachable += 1
            min_z = min(min_z, st[s]["foot_min_z"])
            if tau >= prep:
                min_knee = min(min_knee, st[s]["knee_forward_y"])

        active = None
        if tau >= prep:
            active = next((x for x in steps if x["tau_start"] <= tau < x["tau_end"]), None)
        if active is None:
            if not (lock["L"] and lock["R"]):
                _fail(f"Frame {frame} prep: both feet should be locked: {lock}")
            continue
        k = active["k"]
        local = tau - active["tau_start"]
        sside = active["stance_side"]
        oside = active["swing_side"]
        if local < active["stance_frames"]:
            if not lock[sside] or lock[oside]:
                _fail(f"Frame {frame} stance k={k}: lock state {lock}")
            if local == 0:
                ref[k] = st[sside]["foot_head_world"].copy()
                max_landing = max(max_landing, abs(ref[k].y - stance_y(k)))
            max_drift[sside] = max(max_drift[sside], (st[sside]["foot_head_world"] - ref[k]).length)
        else:
            if lock["L"] or lock["R"]:
                _fail(f"Frame {frame} flight k={k}: feet should be unlocked {lock}")
            airborne_per_step[k] = airborne_per_step.get(k, 0) + 1
            flight_min_z = min(flight_min_z, st["L"]["foot_min_z"], st["R"]["foot_min_z"])
        if tau >= prep + accel + 20:
            steady_pelvis.append(hz)

    v = [(root_y[i + 1] - root_y[i]) * fps for i in range(total - 1)]
    dv = [abs(v[i + 1] - v[i]) for i in range(len(v) - 1)]
    prep_v = max(abs(x) for x in v[:prep])
    accel_v = v[prep:prep + accel]
    mono = all(accel_v[i + 1] >= accel_v[i] - 1e-6 for i in range(len(accel_v) - 1))
    steady_v = v[prep + accel:]
    disp = root_y[-1] - root_y[0]
    pelvis_jump = max(abs(pelvis_z[i + 1] - pelvis_z[i]) for i in range(total - 1))
    pitch_jump = max(abs(pitch[i + 1] - pitch[i]) for i in range(total - 1))
    arm_jump = max(abs(arm_l[i + 1] - arm_l[i]) for i in range(total - 1))
    crouch_drop = pelvis_z[0] - pelvis_z[prep - 1]
    prep_pitch = pitch[prep - 1]
    sprint_pitch = sum(pitch[-40:]) / 40.0
    bounce = max(steady_pelvis) - min(steady_pelvis)

    complete = [s for s in steps if s["tau_end"] <= total]
    first, last = complete[0], complete[-1]
    full_flight_ok = all(airborne_per_step.get(s["k"], 0) == s["flight_frames"] for s in complete)

    print(
        f"Reopened Task 6C Metrics (Frames 1..{total}):\n"
        f"  Root Y {root_y[0]:.4f} -> {root_y[-1]:.4f} m (disp={disp:.4f} m)\n"
        f"  Prep max|v|={prep_v:.6f}; accel monotonic={mono}; v(accel end)={accel_v[-1]:.4f}; "
        f"steady v in [{min(steady_v):.4f}, {max(steady_v):.4f}] m/s; max frame |dv|={max(dv):.4f}\n"
        f"  Step trend: first(D={first['duration_frames']},S={first['stance_frames']},F={first['flight_frames']},L={first['step_length']:.3f}) "
        f"-> last(D={last['duration_frames']},S={last['stance_frames']},F={last['flight_frames']},L={last['step_length']:.3f}); "
        f"cadence {first['cadence_steps_per_s']:.2f} -> {last['cadence_steps_per_s']:.2f} steps/s\n"
        f"  Stance drift L={max_drift['L']:.6f} R={max_drift['R']:.6f} m; landing Y error={max_landing:.6f} m\n"
        f"  Flight min foot Z={flight_min_z:+.4f} m; overall min foot Z={min_z:+.6f} m; min knee fwd={min_knee:+.4f} m\n"
        f"  Max hip-target dist={max_dist:.5f} (limit {MAX_LEG_REACH}); unreachable={unreachable}\n"
        f"  Pose: crouch drop={crouch_drop:.4f} m, prep pitch={prep_pitch:.2f} deg, sprint pitch={sprint_pitch:.2f} deg, "
        f"sprint pelvis bounce range={bounce:.4f} m\n"
        f"  Max per-frame jump: pelvis={pelvis_jump:.5f} m, torso pitch={pitch_jump:.3f} deg, arm={arm_jump:.2f} deg"
    )

    if prep_v > 1e-6: _fail(f"Moved during prep: {prep_v}")
    if not mono: _fail("Acceleration phase not monotonic")
    if max(abs(x - vmax) for x in steady_v) > 1e-3: _fail("Sprint speed not steady")
    if max(dv) > 0.09: _fail(f"Velocity jump {max(dv)}")
    if abs(disp - 6.5833) > 1e-3: _fail(f"Displacement {disp}")
    if not (first["stance_frames"] > last["stance_frames"] and first["flight_frames"] < last["flight_frames"]
            and first["duration_frames"] > last["duration_frames"] and first["step_length"] < last["step_length"]):
        _fail("Gait parameters did not vary as expected")
    if not full_flight_ok: _fail(f"Airborne frames mismatch: {airborne_per_step}")
    if max(max_drift.values()) > 0.001: _fail(f"Stance drift {max_drift}")
    if max_landing > 0.001: _fail(f"Landing error {max_landing}")
    if flight_min_z < 0.01: _fail(f"Flight clearance {flight_min_z}")
    if min_z < -0.001: _fail(f"Ground penetration {min_z}")
    if min_knee < 0.05: _fail(f"Knee direction {min_knee}")
    if unreachable or max_dist > MAX_LEG_REACH + 1e-4: _fail("IK reach violation")
    if crouch_drop < 0.06 or prep_pitch < 15.0: _fail("Insufficient crouch/lean in set pose")
    if not (10.0 < sprint_pitch < 20.0): _fail(f"Sprint pitch {sprint_pitch}")
    if bounce < 0.03: _fail(f"Sprint bounce {bounce}")
    if pelvis_jump > 0.025 or pitch_jump > 3.0 or arm_jump > 20.0: _fail("Pose discontinuity")

    init = create_initial_motion_state(config, start_frame=201, position=(0.0, -3.0, 0.0))
    planner = MotionPlanner(config, armature_obj=arm)
    planner.add_action(SprintStartAction())
    res = planner.execute(initial_state=init)
    fs = res["final_state"]
    if (res["total_frames"] != total or fs.frame != 200 + total or res["unreachable_count"] != 0
            or abs(fs.velocity[1] - vmax) > 1e-4 or fs.mode != MotionMode.SPRINT
            or "foot_L" not in fs.contacts or abs(fs.position[1] - (-3.0 + 6.5833)) > 1e-3):
        _fail(f"Offset planner run failed: frame={fs.frame} v={fs.velocity} mode={fs.mode} y={fs.position}")
    print(f"Verified offset SprintStartAction via MotionPlanner: frames 201..{fs.frame}, final v={fs.velocity}, "
          f"mode={fs.mode.value}, gait_phase={fs.gait_phase:.3f}, y={fs.position[1]:.4f}")
    print("[VERIFY_PASSED] Task 6C sprint start verification completed.")
    print("=== END TASK 6C SPRINT START REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
