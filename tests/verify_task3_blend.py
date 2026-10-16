"""Reopen output/procedural_scene.blend in headless Blender and verify Task 3 elements."""

import sys
import math
import bpy

def verify():
    print("=== START TASK 3 BLEND REOPEN VERIFICATION ===")
    scene = bpy.context.scene
    print(f"Loaded Scene: {scene.name}")
    print(f"Scene Timeline: FPS={scene.render.fps}, Range={scene.frame_start}..{scene.frame_end}")
    print(f"Resolution: {scene.render.resolution_x}x{scene.render.resolution_y}")

    # Check collections
    col_names = [c.name for c in bpy.data.collections]
    print(f"Collections: {col_names}")
    for req_col in ["Environment", "Lighting", "Camera"]:
        if req_col not in col_names:
            print(f"[FAIL] Missing collection: {req_col}", file=sys.stderr)
            sys.exit(1)

    # Check Ground
    ground = scene.objects.get("GroundPlane")
    if not ground:
        print("[FAIL] Missing GroundPlane", file=sys.stderr)
        sys.exit(1)
    top_z = ground.location.z + (ground.dimensions.z / 2.0)
    print(f"Ground Top Z: {top_z:.6f}")
    if abs(top_z) > 1e-4:
        print(f"[FAIL] Ground top face not at Z=0.0: got {top_z}", file=sys.stderr)
        sys.exit(1)

    # Check Environment Objects
    buildings = [obj for obj in scene.objects if obj.name.startswith("BuildingBlock_")]
    pillars = [obj for obj in scene.objects if obj.name.startswith("ObstaclePillar_")]
    waypoints = [obj for obj in scene.objects if obj.name.startswith("WaypointMarker_")]
    print(f"Found: {len(buildings)} buildings, {len(pillars)} pillars, {len(waypoints)} waypoints")
    if len(buildings) < 2 or len(pillars) < 2:
        print("[FAIL] Insufficient environment elements", file=sys.stderr)
        sys.exit(1)

    # Check Lighting
    key_light = scene.objects.get("PipelineKeyLight")
    fill_light = scene.objects.get("PipelineFillLight")
    if not key_light or not fill_light:
        print("[FAIL] Missing KeyLight or FillLight", file=sys.stderr)
        sys.exit(1)
    print(f"Lights: {key_light.name} ({key_light.data.energy}W), {fill_light.name} ({fill_light.data.energy}W)")

    # Check Camera & Constraint & Keyframe Motion
    cam = scene.objects.get("PipelineCamera")
    target = scene.objects.get("CameraLookAtTarget")
    if not cam or not target:
        print("[FAIL] Missing Camera or LookAtTarget", file=sys.stderr)
        sys.exit(1)
    if not cam.constraints.get("Track To"):
        print("[FAIL] Missing Track-To constraint on camera", file=sys.stderr)
        sys.exit(1)

    # Check keyframe motion
    scene.frame_set(1)
    dg = bpy.context.evaluated_depsgraph_get()
    loc1 = tuple(round(c, 4) for c in cam.evaluated_get(dg).location)

    scene.frame_set(180)
    dg = bpy.context.evaluated_depsgraph_get()
    loc180 = tuple(round(c, 4) for c in cam.evaluated_get(dg).location)

    disp = math.hypot(loc180[0] - loc1[0], loc180[1] - loc1[1], loc180[2] - loc1[2])
    print(f"Camera Frame 1 Pos: {loc1}")
    print(f"Camera Frame 180 Pos: {loc180}")
    print(f"Camera Displacement: {disp:.4f}m")
    if disp < 1.0:
        print("[FAIL] Camera keyframe motion not detected on reopen", file=sys.stderr)
        sys.exit(1)

    print("[VERIFY_PASSED] Task 3 .blend reopen verification completed successfully.")
    print("=== END TASK 3 BLEND REOPEN VERIFICATION ===")

if __name__ == "__main__":
    verify()
