"""Minimal Environment Test Script for Blender Headless Execution.

Executed by Blender via: blender.exe -b -P tests/test_env.py
"""

import os
import sys
import bpy
import mathutils

def run_test():
    print("=== START BLENDER ENV TEST ===")
    print(f"Blender Version: {bpy.app.version_string}")
    print(f"Python Version: {sys.version}")
    print(f"bpy module: {bpy.__name__}")
    print(f"mathutils module: {mathutils.__name__}")

    # Determine project root and output directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    blend_path = os.path.join(output_dir, "test_scene.blend")
    render_path = os.path.join(output_dir, "test_render.png")

    # 1. Reset to empty scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "TestScene"

    # 2. Create test cube
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.5))
    cube = bpy.context.active_object
    cube.name = "TestCube"

    # 3. Create basic camera
    bpy.ops.object.camera_add(location=(3.0, -3.0, 2.5), rotation=(1.1, 0.0, 0.785))
    cam = bpy.context.active_object
    cam.name = "TestCamera"
    scene.camera = cam

    # 4. Create basic light
    bpy.ops.object.light_add(type='POINT', location=(2.0, -1.0, 3.0))
    light = bpy.context.active_object
    light.name = "TestLight"
    light.data.energy = 500.0

    # 5. Configure low-cost preview render settings (320x180, Workbench)
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 320
    scene.render.resolution_y = 180
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = render_path

    # 6. Save .blend file
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TEST_OUTPUT] BLEND_FILE_SAVED: {blend_path}")

    # 7. Render test image
    bpy.ops.render.render(write_still=True)
    print(f"[TEST_OUTPUT] RENDER_IMAGE_SAVED: {render_path}")

    # Print summary of created objects
    objects_in_scene = [obj.name for obj in scene.objects]
    print(f"[TEST_OUTPUT] OBJECTS_COUNT: {len(objects_in_scene)}")
    print(f"[TEST_OUTPUT] OBJECTS_LIST: {', '.join(objects_in_scene)}")
    print("=== END BLENDER ENV TEST ===")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"[ERROR] Exception during test execution: {e}", file=sys.stderr)
        sys.exit(1)
