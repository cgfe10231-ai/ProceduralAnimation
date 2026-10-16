"""Lighting setup module for procedural scene illumination."""

import bpy
from typing import Dict
from src.config import PipelineConfig

def setup_lighting(config: PipelineConfig) -> Dict[str, bpy.types.Object]:
    """Create key light, fill light, and ambient environment lighting."""
    scene = bpy.context.scene

    # Lighting collection for hierarchy organization
    light_collection = bpy.data.collections.new("Lighting")
    scene.collection.children.link(light_collection)

    # 1. Main Key Light (Primary directional illumination)
    bpy.ops.object.light_add(type='POINT', location=config.key_light_location)
    key_light = bpy.context.active_object
    key_light.name = "PipelineKeyLight"
    key_light.data.energy = config.key_light_energy
    key_light.data.color = (1.0, 0.96, 0.90)  # Warm key
    scene.collection.objects.unlink(key_light)
    light_collection.objects.link(key_light)

    # 2. Secondary Fill Light (Softens shadows and reveals geometry depth)
    bpy.ops.object.light_add(type='POINT', location=config.fill_light_location)
    fill_light = bpy.context.active_object
    fill_light.name = "PipelineFillLight"
    fill_light.data.energy = config.fill_light_energy
    fill_light.data.color = (0.75, 0.85, 1.0)  # Cool fill
    scene.collection.objects.unlink(fill_light)
    light_collection.objects.link(fill_light)

    # 3. Ambient World Lighting
    if scene.world is None:
        scene.world = bpy.data.worlds.new("ProceduralWorld")
    scene.world.use_nodes = True
    bg_node = scene.world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (0.10, 0.12, 0.15, 1.0)
        bg_node.inputs["Strength"].default_value = 0.6

    return {"key_light": key_light, "fill_light": fill_light}
