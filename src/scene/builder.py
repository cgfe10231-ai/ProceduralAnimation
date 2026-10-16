"""Procedural scene builder implementing the Blender standard coordinate convention.

World Coordinate Convention:
- Z-axis: Up (+Z is sky)
- XY-plane: Ground
- Ground level: Top surface at Z = 0.0
- Units: Meters
"""

from typing import Tuple
import bpy
from src.config import PipelineConfig
from src.scene.layout import SceneLayoutData, generate_environment_layout

def create_simple_material(name: str, color_rgba: tuple) -> bpy.types.Material:
    """Create basic Blender material with a distinct solid color."""
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color_rgba
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = 0.7
    return mat

def setup_scene(config: PipelineConfig, layout: SceneLayoutData = None) -> Tuple[bpy.types.Scene, SceneLayoutData]:
    """Initialize scene, apply timeline/resolution, and build ground & environment."""
    # 1. Reset factory settings with empty scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "ProceduralAnimScene"

    # Set timeline parameters
    scene.render.fps = config.fps
    scene.frame_start = config.frame_start
    scene.frame_end = config.frame_end
    scene.frame_current = config.frame_start

    # Set output dimensions
    scene.render.resolution_x = config.resolution_x
    scene.render.resolution_y = config.resolution_y
    scene.render.resolution_percentage = config.resolution_percentage

    # Generate layout data if not provided
    if layout is None:
        layout = generate_environment_layout(config)

    # Dedicated collection for environment geometry
    env_collection = bpy.data.collections.new("Environment")
    scene.collection.children.link(env_collection)

    # 2. Build Ground Plane / Slab
    gw, gl = layout.ground_size
    gt = layout.ground_thickness
    # Bottom at -gt, top exactly at Z = 0.0
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        scale=(gw, gl, gt),
        location=(0.0, 0.0, -gt / 2.0)
    )
    ground_obj = bpy.context.active_object
    ground_obj.name = "GroundPlane"
    ground_mat = create_simple_material("GroundMaterial", config.ground_color)
    ground_obj.data.materials.append(ground_mat)
    
    # Move to Environment collection
    scene.collection.objects.unlink(ground_obj)
    env_collection.objects.link(ground_obj)

    # 3. Build Environmental Building Blocks
    bld_mat = create_simple_material("BuildingMaterial", config.building_color)
    for b in layout.buildings:
        # Cube size=1.0, scaled to (size_x, size_y, height)
        # Center at (center_x, center_y, height / 2.0) -> base at Z = 0.0
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            scale=(b.size_x, b.size_y, b.height),
            location=(b.center_x, b.center_y, b.height / 2.0)
        )
        bld_obj = bpy.context.active_object
        bld_obj.name = b.name
        bld_obj.data.materials.append(bld_mat)
        scene.collection.objects.unlink(bld_obj)
        env_collection.objects.link(bld_obj)

    # 4. Build Environmental Pillars / Columns
    pillar_mat = create_simple_material("PillarMaterial", config.pillar_color)
    for p in layout.pillars:
        # Cylinder default: r=1, depth=2. scaled to (radius, radius, height/2)
        bpy.ops.mesh.primitive_cylinder_add(
            radius=p.radius,
            depth=p.height,
            location=(p.center_x, p.center_y, p.height / 2.0)
        )
        pil_obj = bpy.context.active_object
        pil_obj.name = p.name
        pil_obj.data.materials.append(pillar_mat)
        scene.collection.objects.unlink(pil_obj)
        env_collection.objects.link(pil_obj)

    # 5. Build Waypoint Corridor Guides (visible path references at Z=0.01)
    guide_mat = create_simple_material("CorridorGuideMaterial", (0.25, 0.65, 0.85, 0.8))
    for i, pt in enumerate(layout.path_points):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.35,
            depth=0.02,
            location=(pt[0], pt[1], 0.01)
        )
        guide_obj = bpy.context.active_object
        guide_obj.name = f"WaypointMarker_{i+1:02d}"
        guide_obj.data.materials.append(guide_mat)
        scene.collection.objects.unlink(guide_obj)
        env_collection.objects.link(guide_obj)

    return scene, layout
