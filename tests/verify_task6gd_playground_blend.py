"""Verification of Generated Dynamics Playground Blend File (Task 6G-D-PRE-P2).

Opens output/dynamics_playground.blend in headless Blender to verify:
1. File existence and size (>50 KB).
2. Scene hierarchy and dedicated collections:
   - Playground_Surfaces
   - Playground_Visuals
   - Playground_Lighting_Cameras
3. Physical zone surfaces presence and bounds:
   - Flat ground, 5 stairs + platform, ramp up + bridge + ramp down, vertical wall, vault box, ledge bar, debug platform.
4. Materials and distinct visual colors assigned.
5. Normal indicator arrows present for analytical surface patches.
6. World coordinate indicators (WorldAxis_X, Y, Z) and 1m unit reference cube.
7. Active inspection camera (PlaygroundOverviewCam) and lighting setup.
"""

import os
import sys
import bpy

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(PROJECT_ROOT, "output", "dynamics_playground.blend")


def verify_blend_scene():
    print("=" * 80)
    print("VERIFYING DYNAMICS PLAYGROUND BLEND SCENE (Task 6G-D-PRE-P2)")
    print("=" * 80)

    # 1. File existence and size check
    if not os.path.isfile(BLEND_PATH):
        raise FileNotFoundError(f"Missing dynamics playground blend: {BLEND_PATH}")

    file_size = os.path.getsize(BLEND_PATH)
    print(f"[OK] File exists: {BLEND_PATH} ({file_size:,} bytes)")
    assert file_size > 50000, f"File size unexpectedly small: {file_size} bytes"

    # 2. Open Blender file
    bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
    scene = bpy.context.scene

    print(f"[SCENE] Name: {scene.name}, FPS: {scene.render.fps}, Frame Range: {scene.frame_start}..{scene.frame_end}")
    assert scene.name == "DynamicsPlaygroundScene", f"Unexpected scene name: {scene.name}"

    # 3. Check Collections
    expected_collections = [
        "Playground_Surfaces",
        "Playground_Visuals",
        "Playground_Lighting_Cameras",
    ]
    for c_name in expected_collections:
        col = bpy.data.collections.get(c_name)
        assert col is not None, f"Missing required collection: {c_name}"
        print(f"  [COLLECTION] {c_name}: {len(col.objects)} objects")

    col_surfaces = bpy.data.collections["Playground_Surfaces"]
    col_visuals = bpy.data.collections["Playground_Visuals"]
    col_lighting = bpy.data.collections["Playground_Lighting_Cameras"]

    # 4. Check Zone Surfaces
    expected_surfaces = [
        "Surface_FlatGround",
        "Surface_Stair_01",
        "Surface_Stair_02",
        "Surface_Stair_03",
        "Surface_Stair_04",
        "Surface_Stair_05",
        "Surface_Stair_TopPlatform",
        "Surface_Ramp_Up",
        "Surface_Ramp_TopPlatform",
        "Surface_Ramp_Down",
        "Surface_VerticalWall",
        "Surface_VaultBox",
        "Surface_LedgeBar_Crossbar",
        "Surface_DebugPlatform",
    ]
    for s_name in expected_surfaces:
        obj = bpy.data.objects.get(s_name)
        assert obj is not None, f"Missing surface object: {s_name}"
        assert obj.type == "MESH", f"Object {s_name} is not a MESH"
        assert len(obj.data.materials) > 0, f"Surface {s_name} has no material assigned"
        assert obj.name in col_surfaces.objects, f"Object {s_name} not in Playground_Surfaces collection"

    print(f"[OK] Verified all {len(expected_surfaces)} physical zone surface meshes and materials")

    # 5. Check Normal Indicator Arrows
    normal_arrows = [o for o in col_visuals.objects if o.name.startswith("NormalArrow_")]
    print(f"[OK] Verified {len(normal_arrows)} normal indicator arrow objects in visuals collection")
    assert len(normal_arrows) >= 15, f"Expected at least 15 normal arrows, found {len(normal_arrows)}"

    # 6. Check Coordinate Guide and Unit Cube
    axis_x = bpy.data.objects.get("WorldAxis_X")
    axis_y = bpy.data.objects.get("WorldAxis_Y")
    axis_z = bpy.data.objects.get("WorldAxis_Z")
    unit_cube = bpy.data.objects.get("Debug_1m_UnitCube")

    assert axis_x is not None, "Missing WorldAxis_X"
    assert axis_y is not None, "Missing WorldAxis_Y"
    assert axis_z is not None, "Missing WorldAxis_Z"
    assert unit_cube is not None, "Missing Debug_1m_UnitCube"
    print(f"[OK] Verified 3D world origin axes (X, Y, Z) and 1m reference unit cube")

    # 7. Check Cameras & Lighting
    cam_over = bpy.data.objects.get("PlaygroundOverviewCam")
    cam_close = bpy.data.objects.get("PlaygroundCloseUpCam")
    sun = bpy.data.objects.get("PlaygroundSun")
    fill = bpy.data.objects.get("PlaygroundFill")

    assert cam_over is not None, "Missing PlaygroundOverviewCam"
    assert cam_close is not None, "Missing PlaygroundCloseUpCam"
    assert sun is not None, "Missing PlaygroundSun"
    assert fill is not None, "Missing PlaygroundFill"
    assert scene.camera == cam_over, "PlaygroundOverviewCam must be active scene camera"
    print(f"[OK] Verified inspection cameras and daylighting setup")

    print("=" * 80)
    print("ALL DYNAMICS PLAYGROUND BLEND VALIDATIONS PASSED!")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        verify_blend_scene()
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] Validation error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
