"""CLI entry point for Task 5C start/accelerate/steady/decelerate/stop prototype."""

import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.motion.start_stop_walk_prototype import run_start_stop_walk_prototype

if __name__ == "__main__":
    run_start_stop_walk_prototype()
