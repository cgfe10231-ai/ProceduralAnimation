"""Task 3 Spatial and Seed Determinism Test Suite.

Can be run directly via Blender Python or host Python.
"""

import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.scene.layout import generate_environment_layout, verify_layout_corridor_clearance

def test_seed_determinism():
    print("[TEST] 1. Testing seed determinism (seed=42)...")
    cfg1 = PipelineConfig(random_seed=42)
    layout1 = generate_environment_layout(cfg1)

    cfg2 = PipelineConfig(random_seed=42)
    layout2 = generate_environment_layout(cfg2)

    # Check identical building positions
    assert len(layout1.buildings) == len(layout2.buildings), "Building count mismatch across identical seed"
    for b1, b2 in zip(layout1.buildings, layout2.buildings):
        assert b1.name == b2.name
        assert b1.center_x == b2.center_x
        assert b1.center_y == b2.center_y
        assert b1.size_x == b2.size_x
        assert b1.size_y == b2.size_y
        assert b1.height == b2.height

    # Check identical pillar positions
    assert len(layout1.pillars) == len(layout2.pillars), "Pillar count mismatch across identical seed"
    for p1, p2 in zip(layout1.pillars, layout2.pillars):
        assert p1.name == p2.name
        assert p1.center_x == p2.center_x
        assert p1.center_y == p2.center_y
        assert p1.radius == p2.radius
        assert p1.height == p2.height

    print("    [PASS] Seed determinism verified: identical coordinates generated.")

def test_seed_variability():
    print("[TEST] 2. Testing seed variability (seed=42 vs seed=99)...")
    cfg_a = PipelineConfig(random_seed=42)
    layout_a = generate_environment_layout(cfg_a)

    cfg_b = PipelineConfig(random_seed=99)
    layout_b = generate_environment_layout(cfg_b)

    # Coordinates must differ
    diff = False
    for b_a, b_b in zip(layout_a.buildings, layout_b.buildings):
        if (b_a.center_x, b_a.center_y) != (b_b.center_x, b_b.center_y):
            diff = True
            break
    assert diff, "Different seeds unexpectedly generated identical building positions!"
    print("    [PASS] Seed variability verified: different seeds produce different layouts.")

def test_corridor_clearance():
    print("[TEST] 3. Testing corridor clearance preservation...")
    for seed in [42, 100, 2026]:
        cfg = PipelineConfig(random_seed=seed)
        layout = generate_environment_layout(cfg)
        cleared = verify_layout_corridor_clearance(layout, cfg.corridor_clearance)
        assert cleared, f"Corridor clearance violated for seed {seed}"
    print("    [PASS] Corridor clearance verified across multiple random seeds.")

if __name__ == "__main__":
    try:
        test_seed_determinism()
        test_seed_variability()
        test_corridor_clearance()
        print("\nALL TASK 3 SPATIAL & DETERMINISM UNIT TESTS PASSED!")
    except Exception as e:
        print(f"[TEST_FAILED] {e}", file=sys.stderr)
        sys.exit(1)
