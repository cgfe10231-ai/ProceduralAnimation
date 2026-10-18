"""CLI entry point for Task 5A: Procedural In-Place Walk Cycle.

Usage:
    blender -b -P run_walk_cycle_prototype.py
"""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.motion.walk_cycle_prototype import run_walk_cycle_prototype


if __name__ == "__main__":
    run_walk_cycle_prototype()
