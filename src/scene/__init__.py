"""Scene building and baseline environment package."""

from .builder import setup_scene
from .layout import generate_environment_layout, verify_layout_corridor_clearance, SceneLayoutData

__all__ = ["setup_scene", "generate_environment_layout", "verify_layout_corridor_clearance", "SceneLayoutData"]
