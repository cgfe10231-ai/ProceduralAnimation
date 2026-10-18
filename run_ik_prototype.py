"""CLI entry point for Task 4C: Procedural Two-Bone Leg IK & Pose Control Prototype.

Usage:
    blender -b -P run_ik_prototype.py
"""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.rig.ik_prototype import run_ik_prototype


if __name__ == "__main__":
    run_ik_prototype()
