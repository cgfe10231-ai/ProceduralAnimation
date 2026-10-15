"""Unified Configuration Management for Procedural Animation Engine."""

import os
from dataclasses import dataclass, field

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

    # Output artifact file names
    blend_filename: str = "procedural_scene.blend"
    preview_image_filename: str = "preview_frame_0001.png"

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

    @property
    def preview_image_path(self) -> str:
        return os.path.join(self.output_dir, self.preview_image_filename)
