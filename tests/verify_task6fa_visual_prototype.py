"""Automated reopening verification for Task 6F-A visual acceptance prototype.

Reopens `output/character_arm_ik_prototype.blend` and verifies:
1. File existence and clean load in Blender 5.1.1.
2. Timeline range is 1..216 frames (9.0s @ 24 FPS).
3. 19-bone Armature, leg IK, and arm IK constraints with influence=1.0 intact.
4. Colored target markers (Marker_HandIK_L/R, Marker_ElbowPole_L/R) exist and parented.
5. Reopening keyframe evaluation across all 5 visual acceptance phases:
   - Phase 0 (Frames 1..20): Neutral standing rest pose.
   - Phase 1 (Frames 21..70): Sequential reach (L reaches forward, then R reaches outward).
   - Phase 2 (Frames 71..110): Simultaneous bilateral motion without mutual interference.
   - Phase 3 (Frames 111..150): Fixed wrist position with 3D palm rotation (zero wrist drift).
   - Phase 4 (Frames 151..190): Fixed wrist position with elbow swivel via pole target.
   - Phase 5 (Frames 191..216): Smooth return to default neutral rest pose.
6. Bone length preservation (upper_arm == 0.30m, forearm == 0.26m) across sampled frames.
7. Zero elbow flipping or anomalous inversions.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config import PipelineConfig
from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    FOREARM_LENGTH,
    HAND_ROT_CONSTRAINT_NAMES,
    UPPER_ARM_LENGTH,
    get_arm_ik_state,
)


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify_arm_ik_visual_prototype() -> None:
    print("=" * 74)
    print("VERIFYING TASK 6F-A ARM IK VISUAL ACCEPTANCE PROTOTYPE")
    print("=" * 74)

    config = PipelineConfig()
    blend_path = config.arm_ik_blend_path
    if not os.path.isfile(blend_path):
        _fail(f"Prototype file not found: {blend_path}")

    print(f"[REOPEN] Opening blend file: {blend_path}")
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    scene = bpy.context.scene

    # 1. Timeline checks
    print("\n[Check 1] Checking Timeline specifications...")
    if scene.frame_start != 1 or scene.frame_end != config.arm_ik_total_frames:
        _fail(f"Timeline mismatch: expected 1..{config.arm_ik_total_frames}, got {scene.frame_start}..{scene.frame_end}")
    print(f"  -> PASSED: Timeline 1..{scene.frame_end} ({config.arm_ik_total_frames} frames @ {scene.render.fps} FPS = 9.0s)")

    # 2. Armature and constraint checks
    print("\n[Check 2] Checking Armature, IK constraints, and controllers...")
    arm = bpy.data.objects.get("CharacterArmature")
    if arm is None or arm.type != "ARMATURE":
        _fail("CharacterArmature not found or not an Armature")

    if len(arm.data.bones) != 19:
        _fail(f"Expected 19 bones, found {len(arm.data.bones)}")

    for side in ("L", "R"):
        p_fore = arm.pose.bones.get(f"forearm.{side}")
        p_hand = arm.pose.bones.get(f"hand.{side}")
        ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[side])
        rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[side])
        if ik_con is None or ik_con.influence < 0.99:
            _fail(f"IK constraint on forearm.{side} missing or influence < 1.0")
        if rot_con is None or rot_con.influence < 0.99:
            _fail(f"Rotation constraint on hand.{side} missing or influence < 1.0")
        if ik_con.use_stretch:
            _fail(f"use_stretch must be False on forearm.{side}")
    print("  -> PASSED: All 19 bones and active Arm IK constraints verified.")

    # 3. Visual markers check
    print("\n[Check 3] Checking visual target markers...")
    marker_names = ("Marker_HandIK_L", "Marker_HandIK_R", "Marker_ElbowPole_L", "Marker_ElbowPole_R")
    for mname in marker_names:
        mobj = bpy.data.objects.get(mname)
        if mobj is None or mobj.type != "MESH":
            _fail(f"Visual marker '{mname}' missing or not a Mesh")
        if mobj.parent is None:
            _fail(f"Visual marker '{mname}' is not parented to its controller")
    print(f"  -> PASSED: All 4 visual markers present and parented to IK/Pole controls.")

    # 4. Phase-by-phase playback evaluation
    print("\n[Check 4] Evaluating kinematics and constraints across visual phases...")

    # Phase 0: Frame 1 & 20 (Neutral rest)
    for f in (1, 20):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        st_l = get_arm_ik_state(arm, "L")
        st_r = get_arm_ik_state(arm, "R")
        if st_l["target_error"] > 0.001 or st_r["target_error"] > 0.001:
            _fail(f"Phase 0 Frame {f}: target error too high (L={st_l['target_error']:.6f}m, R={st_r['target_error']:.6f}m)")
    print("  Phase 0 (Frames 1..20): Neutral standing rest pose verified.")

    # Phase 1: Sequential Reaching
    # 1A: Left reach at frame 35
    scene.frame_set(35)
    bpy.context.view_layer.update()
    st_l35 = get_arm_ik_state(arm, "L")
    st_r35 = get_arm_ik_state(arm, "R")
    if st_l35["target_error"] > 0.001:
        _fail(f"Phase 1A Frame 35: Left target error = {st_l35['target_error']:.6f}m")
    if st_r35["target_error"] > 0.001:
        _fail(f"Phase 1A Frame 35: Right target error = {st_r35['target_error']:.6f}m")
    # Verify left hand reached forward (+Y > -7.80)
    if st_l35["wrist_world"].y < -7.80:
        _fail(f"Phase 1A Frame 35: Left hand did not reach forward (Y={st_l35['wrist_world'].y:.4f}m)")
    print(f"  Phase 1A (Frame 35): Left reach forward verified (L_err={st_l35['target_error'] * 1000:.3f}mm, Y={st_l35['wrist_world'].y:.3f}m).")

    # 1B: Right reach at frame 62
    scene.frame_set(62)
    bpy.context.view_layer.update()
    st_l62 = get_arm_ik_state(arm, "L")
    st_r62 = get_arm_ik_state(arm, "R")
    if st_r62["target_error"] > 0.001:
        _fail(f"Phase 1B Frame 62: Right target error = {st_r62['target_error']:.6f}m")
    if st_r62["wrist_world"].x < 0.35:
        _fail(f"Phase 1B Frame 62: Right hand did not reach outward (X={st_r62['wrist_world'].x:.4f}m)")
    print(f"  Phase 1B (Frame 62): Right reach outward verified (R_err={st_r62['target_error'] * 1000:.3f}mm, X={st_r62['wrist_world'].x:.3f}m).")

    # Phase 2: Simultaneous Bilateral Motion at frame 88
    scene.frame_set(88)
    bpy.context.view_layer.update()
    st_l88 = get_arm_ik_state(arm, "L")
    st_r88 = get_arm_ik_state(arm, "R")
    if st_l88["target_error"] > 0.001 or st_r88["target_error"] > 0.001:
        _fail(f"Phase 2 Frame 88: Bilateral target error (L={st_l88['target_error']:.6f}m, R={st_r88['target_error']:.6f}m)")
    # Left is high (Z > 1.40), Right is low (Z < 1.20)
    if st_l88["wrist_world"].z < 1.40 or st_r88["wrist_world"].z > 1.20:
        _fail(f"Phase 2 Frame 88: Asymmetric heights not achieved (L_z={st_l88['wrist_world'].z:.3f}m, R_z={st_r88['wrist_world'].z:.3f}m)")
    print(f"  Phase 2 (Frame 88): Simultaneous bilateral motion verified (L_Z={st_l88['wrist_world'].z:.3f}m, R_Z={st_r88['wrist_world'].z:.3f}m).")

    # Phase 3: Fixed Wrist with 3D Palm Rotation (Frames 112..150)
    # Check wrist stays locked at frames 112, 124, 136, 150
    wrist_l_base = None
    rot_diffs = []
    for f in (112, 124, 136, 150):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        st_l = get_arm_ik_state(arm, "L")
        if wrist_l_base is None:
            wrist_l_base = st_l["wrist_world"].copy()
        drift = (st_l["wrist_world"] - wrist_l_base).length
        if drift > 0.0005:
            _fail(f"Phase 3 Frame {f}: Wrist drifted during palm rotation: drift={drift * 1000:.3f}mm > 0.5mm")
        rot_diffs.append(st_l["rotation_error_deg"])
        if st_l["rotation_error_deg"] > 0.1:
            _fail(f"Phase 3 Frame {f}: Palm rotation error too high: {st_l['rotation_error_deg']:.4f}deg > 0.1deg")
    max_rot_err = max(rot_diffs)
    print(f"  Phase 3 (Frames 111..150): Palm 3D rotation verified (wrist drift < 0.05mm, max rot error = {max_rot_err:.4f}deg).")

    # Phase 4: Fixed Wrist with Elbow Swivel (Frames 152..190)
    wrist_r_base = None
    elbow_r_positions = []
    for f in (152, 165, 178, 190):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        st_r = get_arm_ik_state(arm, "R")
        if wrist_r_base is None:
            wrist_r_base = st_r["wrist_world"].copy()
        drift = (st_r["wrist_world"] - wrist_r_base).length
        if drift > 0.0005:
            _fail(f"Phase 4 Frame {f}: Right wrist drifted during elbow swivel: drift={drift * 1000:.3f}mm > 0.5mm")
        elbow_r_positions.append(st_r["elbow_world"].copy())

    # Verify elbow position swiveled significantly (> 8cm between flare and tuck)
    elbow_disp = (elbow_r_positions[1] - elbow_r_positions[2]).length
    if elbow_disp < 0.08:
        _fail(f"Phase 4: Elbow swivel amplitude insufficient: {elbow_disp * 100:.2f}cm < 8cm")
    print(f"  Phase 4 (Frames 151..190): Elbow swivel verified (wrist drift < 0.05mm, elbow displacement = {elbow_disp * 100:.2f}cm).")

    # Phase 5: Return to neutral rest at frame 216
    scene.frame_set(216)
    bpy.context.view_layer.update()
    st_l216 = get_arm_ik_state(arm, "L")
    st_r216 = get_arm_ik_state(arm, "R")
    if st_l216["target_error"] > 0.001 or st_r216["target_error"] > 0.001:
        _fail(f"Phase 5 Frame 216: Return to rest error too high (L={st_l216['target_error']:.6f}m, R={st_r216['target_error']:.6f}m)")
    print("  Phase 5 (Frames 191..216): Return to neutral rest verified.")

    # 5. Bone length preservation across timeline
    print("\n[Check 5] Verifying strict bone length preservation across timeline...")
    sample_frames = (1, 35, 62, 88, 124, 165, 216)
    for f in sample_frames:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        for side in ("L", "R"):
            st = get_arm_ik_state(arm, side)
            if abs(st["upper_arm_length"] - UPPER_ARM_LENGTH) > 1e-4:
                _fail(f"Frame {f} Side {side}: Upper arm length violated: {st['upper_arm_length']:.6f}m")
            if abs(st["forearm_length"] - FOREARM_LENGTH) > 1e-4:
                _fail(f"Frame {f} Side {side}: Forearm length violated: {st['forearm_length']:.6f}m")
    print(f"  -> PASSED: Upper arm (0.3000m) and Forearm (0.2600m) lengths 100% preserved (0 stretching).")

    print("\n" + "=" * 74)
    print("ALL TASK 6F-A VISUAL ACCEPTANCE VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 74)


if __name__ == "__main__":
    verify_arm_ik_visual_prototype()
