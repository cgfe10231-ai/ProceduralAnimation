"""CLI entry point for Task 4D: Procedural Support-Foot Locking & Ground Contact Control.

Usage:
    blender -b -P run_foot_contact_prototype.py
"""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.rig.foot_contact_prototype import run_foot_contact_prototype


if __name__ == "__main__":
    run_foot_contact_prototype()
