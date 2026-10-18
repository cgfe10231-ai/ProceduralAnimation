"""Headless entry for Task 4B humanoid armature and binding prototype."""

import os
import sys

try:
    import bpy
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False


def run_in_blender():
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.rig.prototype import run_rig_prototype
    try:
        run_rig_prototype()
    except Exception as exc:
        print(f"[TASK4B_FATAL_ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


def launch_headless_blender():
    import subprocess

    blender_candidates = [
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    ]
    blender_exe = None
    for candidate in blender_candidates:
        if os.path.isfile(candidate):
            blender_exe = candidate
            break
    if not blender_exe:
        import shutil
        blender_exe = shutil.which("blender")
    if not blender_exe:
        print("[ERROR] Blender executable not found.", file=sys.stderr)
        sys.exit(1)

    script_path = os.path.abspath(__file__)
    cmd = [blender_exe, "-b", "-P", script_path]
    print(f"Launching headless Blender Task 4B: {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    if IN_BLENDER:
        run_in_blender()
    else:
        launch_headless_blender()
