"""CLI entry point for Task 5B: Procedural Continuous Forward Walking.

Usage:
    blender -b -P run_forward_walk_prototype.py
"""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.motion.forward_walk_prototype import run_forward_walk_prototype


if __name__ == "__main__":
    run_forward_walk_prototype()
