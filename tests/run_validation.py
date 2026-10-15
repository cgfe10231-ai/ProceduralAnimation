"""Automated Runner and Validator for Blender Environment Test.

Can be run via:
  & "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b --python tests/run_validation.py
or standard Python if available.
"""

import os
import sys
import subprocess
import struct

def find_blender():
    candidates = [
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # Check PATH
    import shutil
    path = shutil.which("blender")
    if path:
        return path
    return None

def get_png_dimensions(file_path):
    with open(file_path, "rb") as f:
        header = f.read(24)
        if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n':
            return None, None
        # IHDR chunk starts at byte 12. Width at 16..20, Height at 20..24
        width, height = struct.unpack(">II", header[16:24])
        return width, height

def main():
    print("=" * 60)
    print("TASK 1 VALIDATION RUNNER: Blender Toolchain Verification")
    print("=" * 60)

    blender_exe = find_blender()
    if not blender_exe:
        print("[FAIL] Blender executable could not be found.")
        sys.exit(1)
    print(f"[1] Blender Executable Located: {blender_exe}")

    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    test_env_script = os.path.join(project_dir, "tests", "test_env.py")
    verify_blend_script = os.path.join(project_dir, "tests", "verify_blend.py")
    output_dir = os.path.join(project_dir, "tests", "output")
    blend_file = os.path.join(output_dir, "test_scene.blend")
    render_file = os.path.join(output_dir, "test_render.png")

    # Step 1: Run test_env.py in headless Blender
    print(f"\n[2] Executing Headless Generation & Render Test...")
    cmd1 = [blender_exe, "-b", "-P", test_env_script]
    res1 = subprocess.run(cmd1, capture_output=True, text=True, cwd=project_dir)
    print(f"    Exit Code: {res1.returncode}")
    if res1.returncode != 0:
        print("[FAIL] Step 1 exited with non-zero code.")
        print(res1.stderr)
        sys.exit(1)
    print("    [PASS] Blender headless script execution completed.")

    # Step 2: Validate .blend artifact
    print(f"\n[3] Validating .blend Artifact: {blend_file}")
    if not os.path.isfile(blend_file):
        print("[FAIL] .blend file does not exist.")
        sys.exit(1)
    blend_size = os.path.getsize(blend_file)
    print(f"    File Size: {blend_size} bytes")
    if blend_size <= 0:
        print("[FAIL] .blend file is empty.")
        sys.exit(1)
    print("    [PASS] .blend file exists and is non-empty.")

    # Step 3: Validate render image artifact
    print(f"\n[4] Validating Render Image: {render_file}")
    if not os.path.isfile(render_file):
        print("[FAIL] Render image file does not exist.")
        sys.exit(1)
    img_size = os.path.getsize(render_file)
    print(f"    File Size: {img_size} bytes")
    if img_size <= 0:
        print("[FAIL] Render image file is empty.")
        sys.exit(1)

    width, height = get_png_dimensions(render_file)
    print(f"    Resolution: {width} x {height}")
    if width != 320 or height != 180:
        print(f"[FAIL] Image dimensions mismatch. Expected 320x180, got {width}x{height}")
        sys.exit(1)
    print("    [PASS] Render image valid with correct resolution (320x180).")

    # Step 4: Reopen .blend in headless Blender and verify scene objects
    print(f"\n[5] Reopening Saved .blend and Verifying Scene Objects...")
    cmd2 = [blender_exe, "-b", blend_file, "-P", verify_blend_script]
    res2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=project_dir)
    print(f"    Exit Code: {res2.returncode}")
    if res2.returncode != 0 or "[VERIFY_PASSED]" not in res2.stdout:
        print("[FAIL] Reopening verification failed.")
        print(res2.stderr)
        print(res2.stdout)
        sys.exit(1)
    print("    [PASS] Reopening verified: TestCube, TestCamera, and TestLight exist and are configured.")

    print("\n" + "=" * 60)
    print("ALL TASK 1 VALIDATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
