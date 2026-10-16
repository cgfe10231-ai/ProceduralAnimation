"""Unified Configuration Management for Procedural Animation Engine."""

import os
from dataclasses import dataclass, field
from typing import Tuple, List

@dataclass
class PipelineConfig:
    """Project-wide configuration parameters."""

    # Project filesystem paths
    project_root: str = field(default_factory=lambda: os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    output_dir_name: str = "output"
    
    # Timeline parameters (Phase 1 Acceptance Defaults)
    fps: int = 24
    frame_start: int = 1
    frame_end: int = 360
    
    # Resolution (1280x720 16:9 HD)
    resolution_x: int = 1280
    resolution_y: int = 720
    resolution_percentage: int = 100
    
    # Render Engine & Quality
    render_engine: str = "BLENDER_WORKBENCH"  # Fast low-cost preview
    preview_samples: int = 1
    file_format: str = "PNG"
    color_mode: str = "RGB"
    
    # Determinism
    random_seed: int = 42

    # Scene & Ground parameters (World Convention: Z=Up, ground top at Z=0.0)
    ground_size: Tuple[float, float] = (24.0, 24.0)  # (width X, length Y) in meters
    ground_thickness: float = 0.2
    ground_color: Tuple[float, float, float, float] = (0.18, 0.20, 0.22, 1.0)

    # Environment layout parameters
    building_count: int = 6
    pillar_count: int = 8
    corridor_clearance: float = 2.4  # Minimum clear distance around character walking path
    building_color: Tuple[float, float, float, float] = (0.45, 0.48, 0.52, 1.0)
    pillar_color: Tuple[float, float, float, float] = (0.75, 0.45, 0.25, 1.0)

    # Reserved character trajectory corridor waypoints:
    # 1. Start / Stand: (0.0, -8.0, 0.0)
    # 2. Walk to Stop/Turn area: (0.0, 0.0, 0.0)
    # 3. Exit direction: towards (3.5, 7.0, 0.0)
    character_path_points: List[Tuple[float, float, float]] = field(
        default_factory=lambda: [(0.0, -8.0, 0.0), (0.0, 0.0, 0.0), (3.5, 7.0, 0.0)]
    )

    # Lighting parameters
    key_light_energy: float = 2500.0
    key_light_location: Tuple[float, float, float] = (8.0, -8.0, 12.0)
    fill_light_energy: float = 800.0
    fill_light_location: Tuple[float, float, float] = (-6.0, 6.0, 8.0)

    # Camera parameters
    camera_focal_length: float = 50.0
    # Preview stills to render and validate across the timeline
    preview_frames: Tuple[int, ...] = (1, 180)

    # Output artifact file names
    blend_filename: str = "procedural_scene.blend"

    @property
    def total_frames(self) -> int:
        return self.frame_end - self.frame_start + 1

    @property
    def output_dir(self) -> str:
        path = os.path.join(self.project_root, self.output_dir_name)
        os.makedirs(path, exist_ok=True)
        return path

    @property
    def blend_file_path(self) -> str:
        return os.path.join(self.output_dir, self.blend_filename)

    def get_preview_image_path(self, frame: int) -> str:
        filename = f"preview_frame_{frame:04d}.png"
        return os.path.join(self.output_dir, filename)

    @property
    def preview_image_path(self) -> str:
        """Default to first preview frame."""
        return self.get_preview_image_path(self.preview_frames[0])
