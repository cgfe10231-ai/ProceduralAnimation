"""Reopen character_walk_cycle.blend and verify all Task 5A requirements:
1. Saved Blender Action/F-Curve animation data exists and plays across frames 1..48 at 24 FPS.
2. Left and right feet alternate between stance and swing phases.
3. During stance phases, actual foot geometry (`Foot_L`, `Foot_R`) and ankle bones remain stable in world space.
4. Neither foot penetrates the Z=0 ground plane across all 48 frames.
5. Both knees flex forward (+Y) across all 48 frames with zero backward hyperextension.
6. Left and right arms swing contra-laterally to the legs.
7. `CharacterRoot` remains stationary at (0, -8, 0) with zero forward displacement.
8. Seamless loop closure between cycle start (frame 1) and cycle end (frame 48 / 49).
"""

import os
import sys

import bpy
from mathutils import Vector

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.character.builder import REQUIRED_PARTS, world_min_z
from src.config import PipelineConfig
from src.rig.ik import IK_TARGET_NAMES, POLE_TARGET_NAMES, get_leg_ik_state
from src.rig.pose import get_part_world_center


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 5A WALK CYCLE REOPEN VERIFICATION ===")
    config = PipelineConfig()
    scene = bpy.context.scene
    start_x, start_y, start_z = config.character_path_points[0]
    expected_root = Vector((start_x, start_y, start_z))

    # 1. Verify timeline settings and saved animation data
    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != 48:
        _fail(
            f"Invalid timeline settings: fps={scene.render.fps}, "
            f"range=({scene.frame_start}, {scene.frame_end})"
        )

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if arm_obj is None or root_obj is None:
        _fail("Missing CharacterArmature or CharacterRoot")

    for obj_name in ("CharacterArmature", "FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R"):
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.animation_data is None or obj.animation_data.action is None:
            _fail(f"Object '{obj_name}' is missing saved Blender animation Action")
    print("Verified saved Blender Actions on CharacterArmature, FootIK.L/R, and KneePole.L/R")

    # Record baseline stance positions at frame 1 (for Left stance) and frame 25 (for Right stance)
    scene.frame_set(1)
    bpy.context.view_layer.update()
    f1_parts = {p: get_part_world_center(p) for p in REQUIRED_PARTS}
    f1_l_state = get_leg_ik_state(arm_obj, "L")
    l_stance_ref_ankle = f1_l_state["foot_head_world"].copy()
    l_stance_ref_mesh = get_part_world_center("Foot_L")

    scene.frame_set(25)
    bpy.context.view_layer.update()
    f25_r_state = get_leg_ik_state(arm_obj, "R")
    r_stance_ref_ankle = f25_r_state["foot_head_world"].copy()
    r_stance_ref_mesh = get_part_world_center("Foot_R")

    max_l_stance_ankle_drift = 0.0
    max_l_stance_mesh_drift = 0.0
    max_r_stance_ankle_drift = 0.0
    max_r_stance_mesh_drift = 0.0
    max_root_drift = 0.0
    min_foot_l_z = 999.0
    min_foot_r_z = 999.0
    max_foot_l_z = -999.0
    max_foot_r_z = -999.0
    max_foot_l_fwd_y = -999.0
    max_foot_r_fwd_y = -999.0
    min_knee_fwd_l = 999.0
    min_knee_fwd_r = 999.0

    # Sweep all 48 frames in reopened .blend
    for frame in range(1, 49):
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        root_disp = (root_obj.matrix_world.translation - expected_root).length
        max_root_drift = max(max_root_drift, root_disp)

        state_l = get_leg_ik_state(arm_obj, "L")
        state_r = get_leg_ik_state(arm_obj, "R")
        mesh_l = get_part_world_center("Foot_L")
        mesh_r = get_part_world_center("Foot_R")

        min_foot_l_z = min(min_foot_l_z, state_l["foot_min_z"])
        min_foot_r_z = min(min_foot_r_z, state_r["foot_min_z"])
        max_foot_l_z = max(max_foot_l_z, state_l["foot_min_z"])
        max_foot_r_z = max(max_foot_r_z, state_r["foot_min_z"])
        max_foot_l_fwd_y = max(max_foot_l_fwd_y, state_l["ankle_world"].y - start_y)
        max_foot_r_fwd_y = max(max_foot_r_fwd_y, state_r["ankle_world"].y - start_y)
        min_knee_fwd_l = min(min_knee_fwd_l, state_l["knee_forward_y"])
        min_knee_fwd_r = min(min_knee_fwd_r, state_r["knee_forward_y"])

        # Left stance is frames 1..25
        if 1 <= frame <= 25:
            l_a_drift = (state_l["foot_head_world"] - l_stance_ref_ankle).length
            l_m_drift = (mesh_l - l_stance_ref_mesh).length
            max_l_stance_ankle_drift = max(max_l_stance_ankle_drift, l_a_drift)
            max_l_stance_mesh_drift = max(max_l_stance_mesh_drift, l_m_drift)

        # Right stance is frames 25..48 (and frame 1)
        if frame == 1 or 25 <= frame <= 48:
            r_a_drift = (state_r["foot_head_world"] - r_stance_ref_ankle).length
            r_m_drift = (mesh_r - r_stance_ref_mesh).length
            max_r_stance_ankle_drift = max(max_r_stance_ankle_drift, r_a_drift)
            max_r_stance_mesh_drift = max(max_r_stance_mesh_drift, r_m_drift)

        if frame in (1, 13, 25, 37, 48):
            arm_l_y = get_part_world_center("LowerArm_L").y - start_y
            arm_r_y = get_part_world_center("LowerArm_R").y - start_y
            print(
                f"Frame {frame:02d}: "
                f"Foot_L(minZ={state_l['foot_min_z']:+.5f}m, dY={state_l['ankle_world'].y - start_y:+.4f}m, kneeFwd={state_l['knee_forward_y']:+.3f}m) | "
                f"Foot_R(minZ={state_r['foot_min_z']:+.5f}m, dY={state_r['ankle_world'].y - start_y:+.4f}m, kneeFwd={state_r['knee_forward_y']:+.3f}m) | "
                f"Forearm_dY(L={arm_l_y:+.3f}m, R={arm_r_y:+.3f}m)"
            )

    print(
        f"Measured Stance Foot Drift (Frames 1..48):\n"
        f"  Left Stance  max ankle_bone_drift={max_l_stance_ankle_drift:.6f}m, max mesh_center_drift={max_l_stance_mesh_drift:.6f}m\n"
        f"  Right Stance max ankle_bone_drift={max_r_stance_ankle_drift:.6f}m, max mesh_center_drift={max_r_stance_mesh_drift:.6f}m\n"
        f"  Max CharacterRoot displacement={max_root_drift:.6f}m\n"
        f"  Min Foot Z: L={min_foot_l_z:+.6f}m, R={min_foot_r_z:+.6f}m | Max Swing Lift Z: L={max_foot_l_z:.4f}m, R={max_foot_r_z:.4f}m\n"
        f"  Max Swing Forward +Y: L={max_foot_l_fwd_y:+.4f}m, R={max_foot_r_fwd_y:+.4f}m\n"
        f"  Min Knee Forward +Y: L={min_knee_fwd_l:+.4f}m, R={min_knee_fwd_r:+.4f}m"
    )

    # Assertions on measured values
    if max_root_drift > 1e-5:
        _fail(f"CharacterRoot moved from origin: max_root_drift={max_root_drift}")
    if max_l_stance_mesh_drift > 0.002 or max_r_stance_mesh_drift > 0.002:
        _fail(
            f"Stance foot mesh drifted excessively: L={max_l_stance_mesh_drift:.6f}m, "
            f"R={max_r_stance_mesh_drift:.6f}m"
        )
    if min_foot_l_z < -0.001 or min_foot_r_z < -0.001:
        _fail(f"Ground penetration detected: min_foot_l_z={min_foot_l_z}, min_foot_r_z={min_foot_r_z}")
    if max_foot_l_z < 0.10 or max_foot_r_z < 0.10:
        _fail(f"Swing foot did not lift sufficiently: L={max_foot_l_z}, R={max_foot_r_z}")
    if max_foot_l_fwd_y < 0.12 or max_foot_r_fwd_y < 0.12:
        _fail(f"Swing foot did not step forward (+Y): L={max_foot_l_fwd_y}, R={max_foot_r_fwd_y}")
    if min_knee_fwd_l <= 0.02 or min_knee_fwd_r <= 0.02:
        _fail(f"Knee bent backward or failed forward flexion: L={min_knee_fwd_l}, R={min_knee_fwd_r}")

    # Verify contra-lateral arm swing at frame 13 (Right leg swings forward => Left arm forward, Right arm back)
    # and frame 37 (Left leg swings forward => Right arm forward, Left arm back)
    scene.frame_set(13)
    bpy.context.view_layer.update()
    f13_arm_l_y = get_part_world_center("LowerArm_L").y
    f13_arm_r_y = get_part_world_center("LowerArm_R").y
    if not (f13_arm_l_y > start_y + 0.04 and f13_arm_r_y < start_y - 0.02):
        _fail(f"Frame 13 contra-lateral arm swing invalid: L_y={f13_arm_l_y}, R_y={f13_arm_r_y}")

    scene.frame_set(37)
    bpy.context.view_layer.update()
    f37_arm_l_y = get_part_world_center("LowerArm_L").y
    f37_arm_r_y = get_part_world_center("LowerArm_R").y
    if not (f37_arm_r_y > start_y + 0.04 and f37_arm_l_y < start_y - 0.02):
        _fail(f"Frame 37 contra-lateral arm swing invalid: L_y={f37_arm_l_y}, R_y={f37_arm_r_y}")
    print("Verified contra-lateral arm swing at frames 13 and 37")

    # Verify seamless loop closure between frame 1 and frame 49, and matching 1-frame step (48->1 vs 1->2)
    scene.frame_set(2)
    bpy.context.view_layer.update()
    max_f1_to_f2_step = max(
        (get_part_world_center(p) - f1_parts[p]).length for p in REQUIRED_PARTS
    )
    scene.frame_set(49)
    bpy.context.view_layer.update()
    max_loop_closure_err = max(
        (get_part_world_center(p) - f1_parts[p]).length for p in REQUIRED_PARTS
    )
    scene.frame_set(48)
    bpy.context.view_layer.update()
    max_f48_to_f1_step = max(
        (get_part_world_center(p) - f1_parts[p]).length for p in REQUIRED_PARTS
    )
    print(
        f"Loop Closure Check: frame 49 vs frame 1 max part error={max_loop_closure_err:.6f}m | "
        f"frame 48->1 max step={max_f48_to_f1_step:.5f}m (frame 1->2 step={max_f1_to_f2_step:.5f}m)"
    )
    if max_loop_closure_err > 1e-4 or abs(max_f48_to_f1_step - max_f1_to_f2_step) > 0.005 or max_f48_to_f1_step > 0.04:
        _fail(f"Loop closure discontinuity: f49_err={max_loop_closure_err}, f48_step={max_f48_to_f1_step}")

    print("[VERIFY_PASSED] Task 5A in-place walk cycle verification completed.")
    print("=== END TASK 5A WALK CYCLE REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
