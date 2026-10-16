"""Deterministic procedural layout generator and path corridor geometry.

Separates geometric layout calculation (pure Python) from Blender object creation.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple
from src.config import PipelineConfig

@dataclass
class BuildingLayout:
    name: str
    center_x: float
    center_y: float
    size_x: float
    size_y: float
    height: float

    @property
    def bounding_radius(self) -> float:
        return math.hypot(self.size_x / 2.0, self.size_y / 2.0)

@dataclass
class PillarLayout:
    name: str
    center_x: float
    center_y: float
    radius: float
    height: float

@dataclass
class SceneLayoutData:
    ground_size: Tuple[float, float]
    ground_thickness: float
    path_points: List[Tuple[float, float, float]]
    buildings: List[BuildingLayout] = field(default_factory=list)
    pillars: List[PillarLayout] = field(default_factory=list)
    random_seed: int = 42

def point_to_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Calculate minimum 2D distance from point (px, py) to line segment (ax, ay) -> (bx, by)."""
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-8:
        return math.hypot(px - ax, py - ay)
    
    # Projection factor clamped to segment [0, 1]
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)

def distance_to_path(px: float, py: float, path_points: List[Tuple[float, float, float]]) -> float:
    """Find minimum distance from point (px, py) to the multi-segment character trajectory."""
    min_dist = float('inf')
    for i in range(len(path_points) - 1):
        ax, ay, _ = path_points[i]
        bx, by, _ = path_points[i + 1]
        dist = point_to_segment_distance(px, py, ax, ay, bx, by)
        if dist < min_dist:
            min_dist = dist
    return min_dist

def generate_environment_layout(config: PipelineConfig) -> SceneLayoutData:
    """Generate deterministic layout data using the seed in config.
    
    Guarantees no environmental obstacle encroaches on the character path corridor.
    """
    rng = random.Random(config.random_seed)
    gw, gl = config.ground_size
    margin = 2.0
    safe_x_range = (-(gw / 2.0) + margin, (gw / 2.0) - margin)
    safe_y_range = (-(gl / 2.0) + margin, (gl / 2.0) - margin)

    layout = SceneLayoutData(
        ground_size=config.ground_size,
        ground_thickness=config.ground_thickness,
        path_points=config.character_path_points,
        random_seed=config.random_seed
    )

    # 1. Place Building Blocks (large rectangular volumes)
    attempts = 0
    max_attempts = 200
    while len(layout.buildings) < config.building_count and attempts < max_attempts:
        attempts += 1
        sx = rng.uniform(2.0, 3.5)
        sy = rng.uniform(2.0, 4.0)
        h = rng.uniform(2.5, 6.0)
        cx = rng.uniform(*safe_x_range)
        cy = rng.uniform(*safe_y_range)

        # Clearance check: distance to character path must exceed corridor_clearance + half-diagonal
        bound_r = math.hypot(sx / 2.0, sy / 2.0)
        dist = distance_to_path(cx, cy, config.character_path_points)
        if dist >= (config.corridor_clearance + bound_r):
            # Avoid excessive overlap with existing buildings
            overlap = False
            for b in layout.buildings:
                if math.hypot(cx - b.center_x, cy - b.center_y) < (bound_r + b.bounding_radius):
                    overlap = True
                    break
            if not overlap:
                idx = len(layout.buildings) + 1
                layout.buildings.append(BuildingLayout(
                    name=f"BuildingBlock_{idx:02d}",
                    center_x=cx,
                    center_y=cy,
                    size_x=sx,
                    size_y=sy,
                    height=h
                ))

    # 2. Place Pillars / Columns (slender vertical obstacles)
    attempts = 0
    while len(layout.pillars) < config.pillar_count and attempts < max_attempts:
        attempts += 1
        r = rng.uniform(0.3, 0.6)
        h = rng.uniform(3.0, 5.0)
        cx = rng.uniform(*safe_x_range)
        cy = rng.uniform(*safe_y_range)

        dist = distance_to_path(cx, cy, config.character_path_points)
        if dist >= (config.corridor_clearance + r):
            idx = len(layout.pillars) + 1
            layout.pillars.append(PillarLayout(
                name=f"ObstaclePillar_{idx:02d}",
                center_x=cx,
                center_y=cy,
                radius=r,
                height=h
            ))

    return layout

def verify_layout_corridor_clearance(layout: SceneLayoutData, clearance: float) -> bool:
    """Mathematically verify all obstacles in layout strictly respect corridor clearance."""
    for b in layout.buildings:
        dist = distance_to_path(b.center_x, b.center_y, layout.path_points)
        if dist < (clearance + b.bounding_radius - 1e-4):
            return False

    for p in layout.pillars:
        dist = distance_to_path(p.center_x, p.center_y, layout.path_points)
        if dist < (clearance + p.radius - 1e-4):
            return False

    return True
