"""Reopen saved .blend file in headless Blender and verify its contents.

Executed via: blender.exe -b <blend_file> -P tests/verify_blend.py
"""

import sys
import bpy

def verify_blend():
    print("=== START BLEND REOPEN VERIFICATION ===")
    scene = bpy.context.scene
    print(f"Loaded Scene Name: {scene.name}")
    
    obj_names = [obj.name for obj in scene.objects]
    print(f"Loaded Object Names: {obj_names}")

    required_objects = ["TestCube", "TestCamera", "TestLight"]
    missing = [name for name in required_objects if name not in obj_names]

    if missing:
        print(f"[VERIFY_FAILED] Missing objects: {missing}", file=sys.stderr)
        sys.exit(1)

    # Check camera assignment
    if not scene.camera or scene.camera.name != "TestCamera":
        print("[VERIFY_FAILED] Scene camera is not set to TestCamera", file=sys.stderr)
        sys.exit(1)

    print("[VERIFY_PASSED] All required objects verified in reopened .blend file.")
    print("=== END BLEND REOPEN VERIFICATION ===")

if __name__ == "__main__":
    verify_blend()
