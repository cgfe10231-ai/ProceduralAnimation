"""Scene building and baseline environment package."""

from .layout import generate_environment_layout, verify_layout_corridor_clearance, SceneLayoutData
from .environment_query import (
    EnvironmentQuery,
    DynamicsEnvironmentQuery,
    OrientedSurface,
    SurfaceGeometryType,
    SurfaceQueryResult,
    create_standard_dynamics_playground_query,
)

try:
    from .builder import setup_scene, build_dynamics_playground
except ImportError:
    setup_scene = None
    build_dynamics_playground = None

__all__ = [
    "setup_scene",
    "build_dynamics_playground",
    "generate_environment_layout",
    "verify_layout_corridor_clearance",
    "SceneLayoutData",
    "EnvironmentQuery",
    "DynamicsEnvironmentQuery",
    "OrientedSurface",
    "SurfaceGeometryType",
    "SurfaceQueryResult",
    "create_standard_dynamics_playground_query",
]
