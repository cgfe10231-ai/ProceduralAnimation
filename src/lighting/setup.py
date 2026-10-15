"""Lighting setup module for procedural scene illumination."""

import bpy
from src.config import PipelineConfig

def setup_lighting(config: PipelineConfig) -> bpy.types.Object:
    """Create basic test key light to illuminate the scene."""
    bpy.ops.object.light_add(type='POINT', location=(3.0, -2.0, 4.0))
    light = bpy.context.active_object
    light.name = "PipelineKeyLight"
    light.data.energy = 800.0
    return light
