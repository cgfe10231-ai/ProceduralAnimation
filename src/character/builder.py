"""Procedural simple humanoid placeholder (Task 4A).

Uses primitive solids only. No armature, no animation, no imported assets.
World convention: Z-up, ground top at Z=0, units in meters.
Feet rest near Z=0. Root XY comes from config.character_path_points[0].
"""

from typing import Dict, List

import bpy
from mathutils import Matrix, Vector

from src.config import PipelineConfig

REQUIRED_PARTS = (
    "Head",
    "Torso",
    "Pelvis",
    "UpperArm_L",
    "UpperArm_R",
    "LowerArm_L",
    "LowerArm_R",
    "UpperLeg_L",
    "UpperLeg_R",
    "LowerLeg_L",
    "LowerLeg_R",
    "Foot_L",
    "Foot_R",
)


def _placeholder_material() -> bpy.types.Material:
    name = "CharacterPlaceholderMaterial"
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        # Neutral clay; style is not locked (DEC-006).
        bsdf.inputs["Base Color"].default_value = (0.62, 0.58, 0.52, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.65
    return mat


def _ensure_character_collection(scene: bpy.types.Scene) -> bpy.types.Collection:
    col = bpy.data.collections.get("Character")
    if col is None:
        col = bpy.data.collections.new("Character")
        scene.collection.children.link(col)
    elif col.name not in [c.name for c in scene.collection.children]:
        scene.collection.children.link(col)
    return col


def _clear_existing_character():
    col = bpy.data.collections.get("Character")
    if col:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    root = bpy.data.objects.get("CharacterRoot")
    if root is not None:
        bpy.data.objects.remove(root, do_unlink=True)


def _link_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection):
    scene = bpy.context.scene
    if obj.name in scene.collection.objects:
        scene.collection.objects.unlink(obj)
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def _parent_keep_local(obj: bpy.types.Object, parent: bpy.types.Object, local_xyz: tuple):
    """Parent so local_xyz is an offset from the root (Z-up, meters)."""
    obj.parent = parent
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.location = Vector(local_xyz)


def _add_cube(
    name: str,
    size_xyz: tuple,
    local_xyz: tuple,
    parent: bpy.types.Object,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, scale=size_xyz, location=(0.0, 0.0, 0.0))
    obj = bpy.context.active_object
    obj.name = name
    if material.name not in [m.name for m in obj.data.materials]:
        obj.data.materials.append(material)
    _link_to_collection(obj, collection)
    _parent_keep_local(obj, parent, local_xyz)
    return obj


def _add_sphere(
    name: str,
    radius: float,
    local_xyz: tuple,
    parent: bpy.types.Object,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0.0, 0.0, 0.0), segments=16, ring_count=8)
    obj = bpy.context.active_object
    obj.name = name
    if material.name not in [m.name for m in obj.data.materials]:
        obj.data.materials.append(material)
    _link_to_collection(obj, collection)
    _parent_keep_local(obj, parent, local_xyz)
    return obj


def character_start_location(config: PipelineConfig) -> tuple:
    """Use the existing Task 3 corridor start waypoint; do not invent a new origin."""
    return tuple(config.character_path_points[0])


def build_character(config: PipelineConfig) -> Dict[str, bpy.types.Object]:
    """Create a standing blocky humanoid at the Task 3 start position."""
    scene = bpy.context.scene
    _clear_existing_character()
    collection = _ensure_character_collection(scene)
    material = _placeholder_material()

    start_x, start_y, start_z = character_start_location(config)
    # start_z is ground (0.0). Root sits on the ground plane.
    root_loc = (start_x, start_y, start_z)

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=root_loc)
    root = bpy.context.active_object
    root.name = "CharacterRoot"
    _link_to_collection(root, collection)

    # Segment heights (meters). Foot bottom at local Z=0 == world Z=start_z.
    foot_h = 0.07
    shin_h = 0.40
    thigh_h = 0.42
    pelvis_h = 0.18
    torso_h = 0.48
    neck_gap = 0.05
    head_r = 0.11

    # Local offsets from CharacterRoot (root at the start waypoint on Z=0).
    z_foot = foot_h / 2.0
    z_shin = foot_h + shin_h / 2.0
    z_thigh = foot_h + shin_h + thigh_h / 2.0
    z_pelvis = foot_h + shin_h + thigh_h + pelvis_h / 2.0
    z_torso = foot_h + shin_h + thigh_h + pelvis_h + torso_h / 2.0
    z_head = foot_h + shin_h + thigh_h + pelvis_h + torso_h + neck_gap + head_r

    hip_x = 0.11
    shoulder_x = 0.24
    z_upper_arm = z_torso + 0.08
    upper_arm_h = 0.30
    lower_arm_h = 0.26
    z_lower_arm = z_upper_arm - upper_arm_h / 2.0 - lower_arm_h / 2.0

    parts: List[bpy.types.Object] = []

    parts.append(_add_sphere("Head", head_r, (0.0, 0.0, z_head), root, collection, material))
    parts.append(_add_cube("Torso", (0.34, 0.20, torso_h), (0.0, 0.0, z_torso), root, collection, material))
    parts.append(_add_cube("Pelvis", (0.32, 0.18, pelvis_h), (0.0, 0.0, z_pelvis), root, collection, material))

    for side, sign in (("L", -1.0), ("R", 1.0)):
        parts.append(_add_cube(
            f"UpperArm_{side}",
            (0.08, 0.08, upper_arm_h),
            (sign * shoulder_x, 0.0, z_upper_arm),
            root, collection, material,
        ))
        parts.append(_add_cube(
            f"LowerArm_{side}",
            (0.07, 0.07, lower_arm_h),
            (sign * shoulder_x, 0.0, z_lower_arm),
            root, collection, material,
        ))
        parts.append(_add_cube(
            f"UpperLeg_{side}",
            (0.11, 0.11, thigh_h),
            (sign * hip_x, 0.0, z_thigh),
            root, collection, material,
        ))
        parts.append(_add_cube(
            f"LowerLeg_{side}",
            (0.09, 0.09, shin_h),
            (sign * hip_x, 0.0, z_shin),
            root, collection, material,
        ))
        # Foot slightly forward (+Y, walking direction of the existing path).
        parts.append(_add_cube(
            f"Foot_{side}",
            (0.10, 0.22, foot_h),
            (sign * hip_x, 0.04, z_foot),
            root, collection, material,
        ))

    bpy.context.view_layer.update()
    result = {"root": root, "parts": {p.name: p for p in parts}}
    print(f"[CHARACTER] Built placeholder at start waypoint {root_loc}")
    print(f"[CHARACTER] Parts: {', '.join(REQUIRED_PARTS)}")
    return result


def world_min_z(obj: bpy.types.Object) -> float:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return min(c.z for c in corners)
