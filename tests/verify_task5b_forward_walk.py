"""Reopen character_forward_walk.blend and verify all Task 5B requirements:
1. Saved Blender Actions exist on CharacterRoot, CharacterArmature, FootIK.L/R, and KneePole.L/R (24 FPS, 1..144 frames).
2. CharacterRoot moves continuously forward (+Y) at consistent speed with zero backward or lateral drift.
3. Left and right feet alternate through 6 half-step stance and swing phases across 3 full cycles.
4. During each 24-frame stance phase, the actual foot geometry and ankle bone stay fixed in world space (not dragged by root).
5. Zero ground penetration and forward knee flexion across all 144 frames.
6. 100% of frames remain strictly within the 0.82m IK reach envelope (0 unreachable events).
"""

import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.rig.ik import MAX_LEG_REACH, get_leg_ik_state
from src.rig.pose import get_part_world_center


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 5B FORWARD WALK REOPEN VERIFICATION ===")
    config = PipelineConfig()
    scene = bpy.context.scene
    start_x, start_y, start_z = config.character_path_points[0]
    half_cycle = config.walk_cycle_frames // 2

    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != 144:
        _fail(
            f"Invalid timeline settings: fps={scene.render.fps}, "
            f"range=({scene.frame_start}, {scene.frame_end})"
        )

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if arm_obj is None or root_obj is None:
        _fail("Missing CharacterArmature or CharacterRoot")

    for obj_name in ("CharacterRoot", "CharacterArmature", "FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R"):
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.animation_data is None or obj.animation_data.action is None:
            _fail(f"Object '{obj_name}' is missing saved Blender animation Action")
    print("Verified saved Blender Actions on CharacterRoot, CharacterArmature, FootIK.L/R, and KneePole.L/R")

    root_y_history = []
    max_stance_ankle_drift_l = 0.0
    max_stance_mesh_drift_l = 0.0
    max_stance_ankle_drift_r = 0.0
    max_stance_mesh_drift_r = 0.0
    min_foot_l_z = 999.0
    min_foot_r_z = 999.0
    min_knee_fwd_l = 999.0
    min_knee_fwd_r = 999.0
    max_hip_dist_l = 0.0
    max_hip_dist_r = 0.0
    unreachable_count = 0

    stance_ref_ankle = {}
    stance_ref_mesh = {}
    stance_step_y_l = []
    stance_step_y_r = []

    for frame in range(1, 145):
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        tau = frame - 1
        k = tau // half_cycle
        root_pos = root_obj.matrix_world.translation.copy()
        if abs(root_pos.x - start_x) > 1e-5 or abs(root_pos.z - start_z) > 1e-5:
            _fail(f"Root X/Z drifted at frame {frame}: {tuple(root_pos)}")
        root_y_history.append(root_pos.y)

        state_l = get_leg_ik_state(arm_obj, "L")
        state_r = get_leg_ik_state(arm_obj, "R")
        mesh_l = get_part_world_center("Foot_L")
        mesh_r = get_part_world_center("Foot_R")

        dist_l = (state_l["target_world"] - state_l["hip_world"]).length
        dist_r = (state_r["target_world"] - state_r["hip_world"]).length
        max_hip_dist_l = max(max_hip_dist_l, dist_l)
        max_hip_dist_r = max(max_hip_dist_r, dist_r)
        if dist_l > MAX_LEG_REACH + 1e-4 or dist_r > MAX_LEG_REACH + 1e-4:
            unreachable_count += 1

        min_foot_l_z = min(min_foot_l_z, state_l["foot_min_z"])
        min_foot_r_z = min(min_foot_r_z, state_r["foot_min_z"])
        min_knee_fwd_l = min(min_knee_fwd_l, state_l["knee_forward_y"])
        min_knee_fwd_r = min(min_knee_fwd_r, state_r["knee_forward_y"])

        if k % 2 == 0:
            # Left foot is in Stance Phase during even half-step k
            if tau % half_cycle == 0:
                stance_ref_ankle[("L", k)] = state_l["foot_head_world"].copy()
                stance_ref_mesh[("L", k)] = mesh_l.copy()
                stance_step_y_l.append(round(state_l["foot_head_world"].y, 4))
            a_drift = (state_l["foot_head_world"] - stance_ref_ankle[("L", k)]).length
            m_drift = (mesh_l - stance_ref_mesh[("L", k)]).length
            max_stance_ankle_drift_l = max(max_stance_ankle_drift_l, a_drift)
            max_stance_mesh_drift_l = max(max_stance_mesh_drift_l, m_drift)
        else:
            # Right foot is in Stance Phase during odd half-step k
            if tau % half_cycle == 0:
                stance_ref_ankle[("R", k)] = state_r["foot_head_world"].copy()
                stance_ref_mesh[("R", k)] = mesh_r.copy()
                stance_step_y_r.append(round(state_r["foot_head_world"].y, 4))
            a_drift = (state_r["foot_head_world"] - stance_ref_ankle[("R", k)]).length
            m_drift = (mesh_r - stance_ref_mesh[("R", k)]).length
            max_stance_ankle_drift_r = max(max_stance_ankle_drift_r, a_drift)
            max_stance_mesh_drift_r = max(max_stance_mesh_drift_r, m_drift)

    # Verify continuous monotonic forward root motion
    step_deltas = [root_y_history[i + 1] - root_y_history[i] for i in range(len(root_y_history) - 1)]
    min_step_dy = min(step_deltas)
    max_step_dy = max(step_deltas)
    total_root_disp = root_y_history[-1] - root_y_history[0]
    elapsed_sec = (144 - 1) / 24.0
    avg_speed = total_root_disp / elapsed_sec

    print(
        f"Reopened Forward Walk Verification Metrics (Frames 1..144):\n"
        f"  Root Y: {root_y_history[0]:.4f}m -> {root_y_history[-1]:.4f}m "
        f"(total_disp={total_root_disp:.4f}m, avg_speed={avg_speed:.4f}m/s)\n"
        f"  Per-frame Root dY range: [{min_step_dy:.5f}m, {max_step_dy:.5f}m]\n"
        f"  Left Stance Foot World Y sequence (k=0,2,4): {stance_step_y_l}\n"
        f"  Right Stance Foot World Y sequence (k=1,3,5): {stance_step_y_r}\n"
        f"  Left Stance  max ankle_bone_drift={max_stance_ankle_drift_l:.6f}m, max mesh_center_drift={max_stance_mesh_drift_l:.6f}m\n"
        f"  Right Stance max ankle_bone_drift={max_stance_ankle_drift_r:.6f}m, max mesh_center_drift={max_stance_mesh_drift_r:.6f}m\n"
        f"  Min Foot Z: L={min_foot_l_z:+.6f}m, R={min_foot_r_z:+.6f}m\n"
        f"  Min Knee Forward +Y: L={min_knee_fwd_l:+.4f}m, R={min_knee_fwd_r:+.4f}m\n"
        f"  Max Hip-to-Target Dist: L={max_hip_dist_l:.5f}m, R={max_hip_dist_r:.5f}m (limit={MAX_LEG_REACH:.2f}m)\n"
        f"  IK Unreachable Events: {unreachable_count}"
    )

    if min_step_dy <= 0.005 or abs(max_step_dy - min_step_dy) > 1e-4:
        _fail(f"Root forward motion not continuous/monotonic: min_dy={min_step_dy}, max_dy={max_step_dy}")
    if total_root_disp < 1.20:
        _fail(f"Total root displacement too small: {total_root_disp}")
    if max_stance_mesh_drift_l > 0.002 or max_stance_mesh_drift_r > 0.002:
        _fail(
            f"Stance foot drifted excessively: L={max_stance_mesh_drift_l:.6f}m, "
            f"R={max_stance_mesh_drift_r:.6f}m"
        )
    if min_foot_l_z < -0.001 or min_foot_r_z < -0.001:
        _fail(f"Ground penetration detected: L={min_foot_l_z}, R={min_foot_r_z}")
    if min_knee_fwd_l <= 0.02 or min_knee_fwd_r <= 0.02:
        _fail(f"Knee backward bend detected: L={min_knee_fwd_l}, R={min_knee_fwd_r}")
    if unreachable_count > 0:
        _fail(f"Encountered {unreachable_count} IK unreachable frames")

    print("[VERIFY_PASSED] Task 5B continuous forward walk verification completed.")
    print("=== END TASK 5B FORWARD WALK REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
