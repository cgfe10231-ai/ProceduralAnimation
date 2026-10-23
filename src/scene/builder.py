"""Procedural scene builder implementing the Blender standard coordinate convention.

World Coordinate Convention:
- Z-axis: Up (+Z is sky)
- XY-plane: Ground
- Ground level: Top surface at Z = 0.0
- Units: Meters

Provides:
- `setup_scene`: Baseline procedural scene builder (Task 3).
- `build_dynamics_playground`: Full 6-zone procedural dynamics training ground (Task 6G-D-PRE-P2).
"""

import math
import os
from typing import Dict, List, Optional, Sequence, Tuple
import bpy

from src.config import PipelineConfig
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    OrientedSurface,
    SurfaceGeometryType,
    create_standard_dynamics_playground_query,
)
from src.scene.layout import SceneLayoutData, generate_environment_layout


# =============================================================================
# Helper Utilities
# =============================================================================

def create_simple_material(name: str, color_rgba: Tuple[float, float, float, float], roughness: float = 0.7) -> bpy.types.Material:
    """Create basic Blender material with a distinct solid color and roughness."""
    mat = bpy.data.materials.get(name)
    if not mat:
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color_rgba
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
    return mat


def create_mesh_object(
    name: str,
    vertices: List[Tuple[float, float, float]],
    faces: List[Sequence[int]],
    collection: bpy.types.Collection,
    material: Optional[bpy.types.Material] = None,
) -> bpy.types.Object:
    """Instantiate a new Blender mesh object from pure Python vertices and faces."""
    mesh_data = bpy.data.meshes.new(name + "_Mesh")
    mesh_data.from_pydata(vertices, [], faces)
    mesh_data.update()
    obj = bpy.data.objects.new(name, mesh_data)
    if material:
        obj.data.materials.append(material)
    collection.objects.link(obj)
    return obj


def create_box_mesh(
    name: str,
    min_xyz: Tuple[float, float, float],
    max_xyz: Tuple[float, float, float],
    collection: bpy.types.Collection,
    material: Optional[bpy.types.Material] = None,
) -> bpy.types.Object:
    """Create an axis-aligned 3D solid box mesh."""
    x0, y0, z0 = min_xyz
    x1, y1, z1 = max_xyz
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # 0..3 Bottom
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # 4..7 Top
    ]
    faces = [
        (0, 3, 2, 1),  # Bottom (-Z)
        (4, 5, 6, 7),  # Top (+Z)
        (0, 1, 5, 4),  # Front (-Y)
        (2, 3, 7, 6),  # Back (+Y)
        (0, 4, 7, 3),  # Left (-X)
        (1, 2, 6, 5),  # Right (+X)
    ]
    return create_mesh_object(name, verts, faces, collection, material)


def create_arrow_mesh(
    name: str,
    origin: Tuple[float, float, float],
    direction: Tuple[float, float, float],
    length: float = 0.50,
    stem_radius: float = 0.025,
    head_length: float = 0.15,
    head_radius: float = 0.065,
    collection: bpy.types.Collection = None,
    material: Optional[bpy.types.Material] = None,
) -> bpy.types.Object:
    """Generate a 3D directional arrow (cylindrical stem + conical tip) pointing along direction."""
    dx, dy, dz = direction
    d_len = math.sqrt(dx * dx + dy * dy + dz * dz)
    if d_len < 1e-8:
        direction = (0.0, 0.0, 1.0)
    else:
        direction = (dx / d_len, dy / d_len, dz / d_len)

    # Compute orthogonal basis (u, v, dir)
    nx, ny, nz = direction
    abs_d = (abs(nx), abs(ny), abs(nz))
    min_idx = abs_d.index(min(abs_d))
    ref = [0.0, 0.0, 0.0]
    ref[min_idx] = 1.0

    # u = ref x dir
    ux = ref[1] * nz - ref[2] * ny
    uy = ref[2] * nx - ref[0] * nz
    uz = ref[0] * ny - ref[1] * nx
    u_len = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / u_len, uy / u_len, uz / u_len

    # v = dir x u
    vx = ny * uz - nz * uy
    vy = nz * ux - nx * uz
    vz = nx * uy - ny * ux

    ox, oy, oz = origin
    stem_len = max(0.05, length - head_length)

    verts: List[Tuple[float, float, float]] = []
    num_sides = 6
    for i in range(num_sides):
        angle = 2.0 * math.pi * i / num_sides
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        # Stem base (ring 0)
        verts.append((
            ox + stem_radius * (cos_a * ux + sin_a * vx),
            oy + stem_radius * (cos_a * uy + sin_a * vy),
            oz + stem_radius * (cos_a * uz + sin_a * vz),
        ))
        # Stem top (ring 1)
        verts.append((
            ox + stem_len * nx + stem_radius * (cos_a * ux + sin_a * vx),
            oy + stem_len * ny + stem_radius * (cos_a * uy + sin_a * vy),
            oz + stem_len * nz + stem_radius * (cos_a * uz + sin_a * vz),
        ))
        # Cone base (ring 2)
        verts.append((
            ox + stem_len * nx + head_radius * (cos_a * ux + sin_a * vx),
            oy + stem_len * ny + head_radius * (cos_a * uy + sin_a * vy),
            oz + stem_len * nz + head_radius * (cos_a * uz + sin_a * vz),
        ))

    # Tip point (vertex 3 * num_sides)
    tip_idx = 3 * num_sides
    verts.append((
        ox + length * nx,
        oy + length * ny,
        oz + length * nz,
    ))

    faces: List[Sequence[int]] = []
    for i in range(num_sides):
        nxt = (i + 1) % num_sides
        b0 = i * 3
        t0 = i * 3 + 1
        c0 = i * 3 + 2
        b1 = nxt * 3
        t1 = nxt * 3 + 1
        c1 = nxt * 3 + 2

        # Stem side quad
        faces.append((b0, b1, t1, t0))
        # Cone side triangle
        faces.append((c0, c1, tip_idx))
        # Cone base annular ring
        faces.append((t0, t1, c1, c0))

    return create_mesh_object(name, verts, faces, collection, material)


# =============================================================================
# Legacy Task 3 Scene Builder
# =============================================================================

def setup_scene(config: PipelineConfig, layout: SceneLayoutData = None) -> Tuple[bpy.types.Scene, SceneLayoutData]:
    """Initialize scene, apply timeline/resolution, and build ground & environment (Task 3)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "ProceduralAnimScene"

    scene.render.fps = config.fps
    scene.frame_start = config.frame_start
    scene.frame_end = config.frame_end
    scene.frame_current = config.frame_start

    scene.render.resolution_x = config.resolution_x
    scene.render.resolution_y = config.resolution_y
    scene.render.resolution_percentage = config.resolution_percentage

    if layout is None:
        layout = generate_environment_layout(config)

    env_collection = bpy.data.collections.new("Environment")
    scene.collection.children.link(env_collection)

    gw, gl = layout.ground_size
    gt = layout.ground_thickness
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        scale=(gw, gl, gt),
        location=(0.0, 0.0, -gt / 2.0)
    )
    ground_obj = bpy.context.active_object
    ground_obj.name = "GroundPlane"
    ground_mat = create_simple_material("GroundMaterial", config.ground_color)
    ground_obj.data.materials.append(ground_mat)
    
    scene.collection.objects.unlink(ground_obj)
    env_collection.objects.link(ground_obj)

    bld_mat = create_simple_material("BuildingMaterial", config.building_color)
    for b in layout.buildings:
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

    pillar_mat = create_simple_material("PillarMaterial", config.pillar_color)
    for p in layout.pillars:
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

    return scene, layout


# =============================================================================
# Task 6G-D-PRE-P2: Procedural Dynamics Playground Scene Builder
# =============================================================================

def build_dynamics_playground(
    query: Optional[DynamicsEnvironmentQuery] = None,
    output_path: Optional[str] = None,
) -> Tuple[bpy.types.Scene, DynamicsEnvironmentQuery]:
    """Generate complete 6-zone Procedural Dynamics Training Ground in Blender.

    Features:
    1. Flat Ground: Walk/Run reference baseline.
    2. Standard Stairs: 5 steps with distinct treads and risers + top landing platform.
    3. Sloped Ramps: +15 deg ramp up, connector bridge, -20 deg ramp down.
    4. Vertical Wall: 2.5m high obstacle with front impact face and top ledge.
    5. Vault Platform & Ledge Bar: 0.9m box and 2.2m overhead suspension bar.
    6. Telemetry Debug Hub: Reference slab with 3D coordinate axes and 1m unit cube.
    - Outward normal indicator arrows for every analytical surface.
    - Dual inspection cameras and three-point daylight setup.

    Returns:
        (bpy.types.Scene, DynamicsEnvironmentQuery)
    """
    if query is None:
        query = create_standard_dynamics_playground_query()

    # 1. Reset factory settings with empty scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "DynamicsPlaygroundScene"

    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 100
    scene.frame_current = 1
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    # 2. Setup Dedicated Collections
    col_surfaces = bpy.data.collections.new("Playground_Surfaces")
    col_visuals = bpy.data.collections.new("Playground_Visuals")
    col_lighting = bpy.data.collections.new("Playground_Lighting_Cameras")

    scene.collection.children.link(col_surfaces)
    scene.collection.children.link(col_visuals)
    scene.collection.children.link(col_lighting)

    # 3. Create Dedicated Shaders / Materials
    mat_ground = create_simple_material("Mat_Ground", (0.35, 0.35, 0.38, 1.0), roughness=0.85)
    mat_stairs = create_simple_material("Mat_Stairs", (0.22, 0.58, 0.82, 1.0), roughness=0.60)
    mat_ramp = create_simple_material("Mat_Ramp", (0.92, 0.52, 0.12, 1.0), roughness=0.60)
    mat_wall = create_simple_material("Mat_Wall", (0.82, 0.22, 0.22, 1.0), roughness=0.70)
    mat_box = create_simple_material("Mat_Box", (0.55, 0.20, 0.82, 1.0), roughness=0.60)
    mat_ledge = create_simple_material("Mat_Ledge", (0.20, 0.25, 0.32, 1.0), roughness=0.40)
    mat_debug = create_simple_material("Mat_DebugPlatform", (0.85, 0.82, 0.25, 1.0), roughness=0.50)
    mat_cube = create_simple_material("Mat_UnitCube", (0.95, 0.95, 0.95, 1.0), roughness=0.30)
    mat_arrow = create_simple_material("Mat_NormalArrow", (0.0, 0.90, 1.0, 1.0), roughness=0.30)
    mat_axis_x = create_simple_material("Mat_Axis_X", (1.0, 0.1, 0.1, 1.0), roughness=0.20)
    mat_axis_y = create_simple_material("Mat_Axis_Y", (0.1, 1.0, 0.1, 1.0), roughness=0.20)
    mat_axis_z = create_simple_material("Mat_Axis_Z", (0.1, 0.4, 1.0, 1.0), roughness=0.20)

    # 4. Construct Solid Meshes for Each Zone

    # Zone 1: Flat Ground Plane (X in [-10, 10], Y in [-10, 5], Top at Z=0.0)
    create_box_mesh(
        name="Surface_FlatGround",
        min_xyz=(-10.0, -10.0, -0.30),
        max_xyz=(10.0, 5.0, 0.0),
        collection=col_surfaces,
        material=mat_ground,
    )

    # Zone 2: Stairs (5 Steps + Platform)
    tread_d = 0.30
    riser_h = 0.15
    stair_y0 = 6.0
    for i in range(5):
        s_y0 = stair_y0 + i * tread_d
        s_y1 = s_y0 + tread_d
        s_z = (i + 1) * riser_h
        create_box_mesh(
            name=f"Surface_Stair_{i+1:02d}",
            min_xyz=(-3.0, s_y0, 0.0),
            max_xyz=(3.0, s_y1, s_z),
            collection=col_surfaces,
            material=mat_stairs,
        )

    # Stairs Top Landing Platform (Y in [7.5, 10.0], Z=0.75m)
    create_box_mesh(
        name="Surface_Stair_TopPlatform",
        min_xyz=(-3.0, 7.5, 0.0),
        max_xyz=(3.0, 10.0, 5 * riser_h),
        collection=col_surfaces,
        material=mat_stairs,
    )

    # Zone 3: Sloped Ramps (Up 15 deg, Platform, Down 20 deg)
    # Ramp Up solid prism (Y in [11.0, 16.0], Z from 0 to 1.3397m)
    ramp_up_top_z = 5.0 * math.tan(math.radians(15.0))  # 1.3397m
    ramp_up_verts = [
        (-3.0, 11.0, 0.0), (3.0, 11.0, 0.0),  # 0, 1 Bottom front
        (3.0, 16.0, 0.0), (-3.0, 16.0, 0.0),  # 2, 3 Bottom back
        (3.0, 16.0, ramp_up_top_z), (-3.0, 16.0, ramp_up_top_z),  # 4, 5 Top back ridge
    ]
    ramp_up_faces = [
        (0, 3, 2, 1),  # Base
        (2, 3, 5, 4),  # Back vertical wall
        (0, 1, 4, 5),  # Sloped top tread
        (0, 5, 3),     # Left triangular side
        (1, 2, 4),     # Right triangular side
    ]
    create_mesh_object("Surface_Ramp_Up", ramp_up_verts, ramp_up_faces, col_surfaces, mat_ramp)

    # Ramp Bridge Platform (Y in [16.0, 18.0], Z=1.3397m)
    create_box_mesh(
        name="Surface_Ramp_TopPlatform",
        min_xyz=(-3.0, 16.0, 0.0),
        max_xyz=(3.0, 18.0, ramp_up_top_z),
        collection=col_surfaces,
        material=mat_ramp,
    )

    # Ramp Down solid prism (Y in [18.0, 21.681], Z from 1.3397m down to 0)
    ramp_down_len_y = ramp_up_top_z / math.tan(math.radians(20.0))  # 3.681m
    ramp_down_end_y = 18.0 + ramp_down_len_y
    ramp_down_verts = [
        (-3.0, 18.0, 0.0), (3.0, 18.0, 0.0),              # 0, 1 Bottom front
        (3.0, ramp_down_end_y, 0.0), (-3.0, ramp_down_end_y, 0.0),  # 2, 3 Bottom end
        (3.0, 18.0, ramp_up_top_z), (-3.0, 18.0, ramp_up_top_z),  # 4, 5 Top ridge
    ]
    ramp_down_faces = [
        (0, 3, 2, 1),  # Base
        (0, 1, 4, 5),  # Front vertical wall
        (4, 2, 3, 5),  # Sloped downhill surface
        (0, 5, 3),     # Left side
        (1, 2, 4),     # Right side
    ]
    create_mesh_object("Surface_Ramp_Down", ramp_down_verts, ramp_down_faces, col_surfaces, mat_ramp)

    # Zone 4: Vertical Wall (Y=24.0m, Z in [0, 2.5]m, thickness 0.4m)
    create_box_mesh(
        name="Surface_VerticalWall",
        min_xyz=(-3.0, 23.8, 0.0),
        max_xyz=(3.0, 24.2, 2.50),
        collection=col_surfaces,
        material=mat_wall,
    )

    # Zone 5: Vault Box & Overhead Ledge Bar
    # Vault Box (Y in [26.5, 29.5], Height 0.90m)
    create_box_mesh(
        name="Surface_VaultBox",
        min_xyz=(-2.5, 26.5, 0.0),
        max_xyz=(2.5, 29.5, 0.90),
        collection=col_surfaces,
        material=mat_box,
    )

    # Overhead Ledge Bar (Crossbar at Y=32.0, Z=2.20m + 2 vertical support posts)
    bar_y = 32.0
    bar_z = 2.20
    # Crossbar
    create_box_mesh(
        name="Surface_LedgeBar_Crossbar",
        min_xyz=(-2.0, bar_y - 0.05, bar_z - 0.05),
        max_xyz=(2.0, bar_y + 0.05, bar_z + 0.05),
        collection=col_surfaces,
        material=mat_ledge,
    )
    # Left support post
    create_box_mesh(
        name="Support_LedgeBar_Post_L",
        min_xyz=(-2.05, bar_y - 0.05, 0.0),
        max_xyz=(-1.95, bar_y + 0.05, bar_z),
        collection=col_surfaces,
        material=mat_ledge,
    )
    # Right support post
    create_box_mesh(
        name="Support_LedgeBar_Post_R",
        min_xyz=(1.95, bar_y - 0.05, 0.0),
        max_xyz=(2.05, bar_y + 0.05, bar_z),
        collection=col_surfaces,
        material=mat_ledge,
    )

    # Zone 6: Telemetry Debug Hub (Slab at X in [5, 9], Y in [-5, -1])
    create_box_mesh(
        name="Surface_DebugPlatform",
        min_xyz=(5.0, -5.0, 0.0),
        max_xyz=(9.0, -1.0, 0.05),
        collection=col_surfaces,
        material=mat_debug,
    )
    # 1.0m Reference Unit Cube (at center (7.0, -3.0), Z in [0.05, 1.05])
    create_box_mesh(
        name="Debug_1m_UnitCube",
        min_xyz=(6.5, -3.5, 0.05),
        max_xyz=(7.5, -2.5, 1.05),
        collection=col_visuals,
        material=mat_cube,
    )

    # 3D Coordinate Axis Indicators at Origin (0, 0, 0)
    create_box_mesh("WorldAxis_X", (0.0, -0.04, 0.0), (2.0, 0.04, 0.08), col_visuals, mat_axis_x)
    create_box_mesh("WorldAxis_Y", (-0.04, 0.0, 0.0), (0.04, 2.0, 0.08), col_visuals, mat_axis_y)
    create_box_mesh("WorldAxis_Z", (-0.04, -0.04, 0.0), (0.04, 0.04, 2.0), col_visuals, mat_axis_z)

    # 5. Build Normal Indicator Arrows for All Registered Analytical Surfaces
    for s in query.get_all_surfaces():
        arrow_origin = s.center
        arrow_name = f"NormalArrow_{s.surface_id}"
        create_arrow_mesh(
            name=arrow_name,
            origin=arrow_origin,
            direction=s.normal,
            length=0.45,
            stem_radius=0.02,
            head_length=0.12,
            head_radius=0.05,
            collection=col_visuals,
            material=mat_arrow,
        )

    # 6. Cameras & Lighting Setup
    # Main Overview Camera (Sweeping corridor view from elevated front angle)
    cam_over_data = bpy.data.cameras.new("PlaygroundOverviewCam")
    cam_over_data.lens = 28
    cam_over_obj = bpy.data.objects.new("PlaygroundOverviewCam", cam_over_data)
    cam_over_obj.location = (16.0, -8.0, 14.0)
    # Look down corridor
    cam_over_obj.rotation_euler = (math.radians(60.0), 0.0, math.radians(65.0))
    col_lighting.objects.link(cam_over_obj)
    scene.camera = cam_over_obj

    # Closeup Camera for Ramp and Wall Interaction
    cam_close_data = bpy.data.cameras.new("PlaygroundCloseUpCam")
    cam_close_data.lens = 35
    cam_close_obj = bpy.data.objects.new("PlaygroundCloseUpCam", cam_close_data)
    cam_close_obj.location = (6.5, 20.0, 3.5)
    cam_close_obj.rotation_euler = (math.radians(75.0), 0.0, math.radians(70.0))
    col_lighting.objects.link(cam_close_obj)

    # Sunlight
    sun_data = bpy.data.lights.new("PlaygroundSun", type="SUN")
    sun_data.energy = 3.5
    sun_data.color = (1.0, 0.98, 0.92)
    sun_obj = bpy.data.objects.new("PlaygroundSun", sun_data)
    sun_obj.location = (12.0, -6.0, 22.0)
    sun_obj.rotation_euler = (math.radians(45.0), math.radians(20.0), math.radians(35.0))
    col_lighting.objects.link(sun_obj)

    # Fill Light
    fill_data = bpy.data.lights.new("PlaygroundFill", type="SUN")
    fill_data.energy = 1.5
    fill_data.color = (0.85, 0.92, 1.0)
    fill_obj = bpy.data.objects.new("PlaygroundFill", fill_data)
    fill_obj.location = (-10.0, 25.0, 15.0)
    fill_obj.rotation_euler = (math.radians(60.0), math.radians(-30.0), math.radians(-45.0))
    col_lighting.objects.link(fill_obj)

    # Save to file if output_path specified
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(output_path))
        print(f"[OK] Dynamics Playground blend saved to: {output_path}")

    return scene, query


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
