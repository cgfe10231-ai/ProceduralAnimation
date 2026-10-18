"""Procedural humanoid armature construction and rigid body-part binding (Task 4B).

Builds a 19-bone Blender Armature aligned to the existing 13-part Task 4A humanoid
placeholder at the start waypoint (0.0, -8.0, 0.0) with Z=0 ground convention.

Coordinate & Bone Axis Convention:
- World: Z-up, +Y forward (walking direction), +X right, ground top at Z=0.0 (meters).
- Bone naming: Blender standard `.L` (left, -X) and `.R` (right, +X) suffixes.
- Bone local axes:
  - Longitudinal axis is Bone +Y (head -> tail).
  - For spine/neck/head, arms, legs, and feet, Bone +X is aligned with World +X (Right),
    so local X rotation is always sagittal pitch (forward/backward swing),
    local Y rotation is axial twist, and local Z rotation is coronal roll/abduction.
"""

from typing import Dict, Tuple
import bpy
from mathutils import Matrix, Vector

from src.config import PipelineConfig
from src.character.builder import REQUIRED_PARTS, character_start_location

# Ordered bone definitions:
# (bone_name, parent_name, head_local_xyz, tail_local_xyz, use_connect, roll_up_vec)
BONE_SPECIFICATIONS: Tuple[Tuple[str, str, tuple, tuple, bool, tuple], ...] = (
    # Central axial hierarchy
    ("root", None, (0.0, 0.0, 0.0), (0.0, 0.0, 0.20), False, (0.0, -1.0, 0.0)),
    ("pelvis", "root", (0.0, 0.0, 0.89), (0.0, 0.0, 1.07), False, (0.0, -1.0, 0.0)),
    ("spine", "pelvis", (0.0, 0.0, 1.07), (0.0, 0.0, 1.55), True, (0.0, -1.0, 0.0)),
    ("neck", "spine", (0.0, 0.0, 1.55), (0.0, 0.0, 1.60), True, (0.0, -1.0, 0.0)),
    ("head", "neck", (0.0, 0.0, 1.60), (0.0, 0.0, 1.82), True, (0.0, -1.0, 0.0)),
    # Left arm chain (-X)
    ("shoulder.L", "spine", (-0.06, 0.0, 1.54), (-0.24, 0.0, 1.54), False, (0.0, 0.0, 1.0)),
    ("upper_arm.L", "shoulder.L", (-0.24, 0.0, 1.54), (-0.24, 0.0, 1.24), True, (0.0, 1.0, 0.0)),
    ("forearm.L", "upper_arm.L", (-0.24, 0.0, 1.24), (-0.24, 0.0, 0.98), True, (0.0, 1.0, 0.0)),
    ("hand.L", "forearm.L", (-0.24, 0.0, 0.98), (-0.24, 0.0, 0.88), True, (0.0, 1.0, 0.0)),
    # Right arm chain (+X)
    ("shoulder.R", "spine", (0.06, 0.0, 1.54), (0.24, 0.0, 1.54), False, (0.0, 0.0, 1.0)),
    ("upper_arm.R", "shoulder.R", (0.24, 0.0, 1.54), (0.24, 0.0, 1.24), True, (0.0, 1.0, 0.0)),
    ("forearm.R", "upper_arm.R", (0.24, 0.0, 1.24), (0.24, 0.0, 0.98), True, (0.0, 1.0, 0.0)),
    ("hand.R", "forearm.R", (0.24, 0.0, 0.98), (0.24, 0.0, 0.88), True, (0.0, 1.0, 0.0)),
    # Left leg chain (-X)
    ("thigh.L", "pelvis", (-0.11, 0.0, 0.89), (-0.11, 0.0, 0.47), False, (0.0, 1.0, 0.0)),
    ("shin.L", "thigh.L", (-0.11, 0.0, 0.47), (-0.11, 0.0, 0.07), True, (0.0, 1.0, 0.0)),
    ("foot.L", "shin.L", (-0.11, 0.0, 0.07), (-0.11, 0.15, 0.035), True, (0.0, 0.0, 1.0)),
    # Right leg chain (+X)
    ("thigh.R", "pelvis", (0.11, 0.0, 0.89), (0.11, 0.0, 0.47), False, (0.0, 1.0, 0.0)),
    ("shin.R", "thigh.R", (0.11, 0.0, 0.47), (0.11, 0.0, 0.07), True, (0.0, 1.0, 0.0)),
    ("foot.R", "shin.R", (0.11, 0.0, 0.07), (0.11, 0.15, 0.035), True, (0.0, 0.0, 1.0)),
)

# Parent-child lookup dictionary for validation and introspection
BONE_HIERARCHY: Dict[str, str] = {
    bone_name: parent_name for bone_name, parent_name, _, _, _, _ in BONE_SPECIFICATIONS
}

# Mapping from the 13 Task 4A body part mesh names to their controlling bone names
PART_TO_BONE_MAP: Dict[str, str] = {
    "Pelvis": "pelvis",
    "Torso": "spine",
    "Head": "head",
    "UpperArm_L": "upper_arm.L",
    "UpperArm_R": "upper_arm.R",
    "LowerArm_L": "forearm.L",
    "LowerArm_R": "forearm.R",
    "UpperLeg_L": "thigh.L",
    "UpperLeg_R": "thigh.R",
    "LowerLeg_L": "shin.L",
    "LowerLeg_R": "shin.R",
    "Foot_L": "foot.L",
    "Foot_R": "foot.R",
}


def _clear_existing_armature():
    existing = bpy.data.objects.get("CharacterArmature")
    if existing is not None:
        arm_data = existing.data
        bpy.data.objects.remove(existing, do_unlink=True)
        if arm_data and arm_data.users == 0:
            bpy.data.armatures.remove(arm_data)


def build_rig(config: PipelineConfig, character_root: bpy.types.Object = None) -> bpy.types.Object:
    """Create the procedural humanoid Armature aligned to the existing character."""
    scene = bpy.context.scene
    _clear_existing_armature()

    if character_root is None:
        character_root = bpy.data.objects.get("CharacterRoot")

    if character_root is not None:
        origin_xyz = tuple(character_root.location)
    else:
        origin_xyz = character_start_location(config)

    arm_data = bpy.data.armatures.new("CharacterArmatureData")
    arm_obj = bpy.data.objects.new("CharacterArmature", arm_data)
    arm_obj.location = Vector(origin_xyz)
    arm_obj.rotation_mode = "XYZ"

    # Link to Character collection if present, else scene root collection
    char_col = bpy.data.collections.get("Character")
    if char_col is not None:
        char_col.objects.link(arm_obj)
    else:
        scene.collection.objects.link(arm_obj)

    # Parent CharacterArmature to CharacterRoot so root hierarchy remains unified
    if character_root is not None:
        arm_obj.parent = character_root
        arm_obj.matrix_parent_inverse = Matrix.Identity(4)
        arm_obj.location = Vector((0.0, 0.0, 0.0))

    # Enter Edit Mode on the Armature to construct bones
    bpy.ops.object.select_all(action="DESELECT")
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = arm_data.edit_bones
    for bone_name, parent_name, head_xyz, tail_xyz, use_connect, roll_vec in BONE_SPECIFICATIONS:
        ebone = edit_bones.new(bone_name)
        ebone.head = Vector(head_xyz)
        ebone.tail = Vector(tail_xyz)
        if parent_name is not None:
            ebone.parent = edit_bones[parent_name]
            ebone.use_connect = use_connect
        else:
            ebone.use_connect = False
        ebone.align_roll(Vector(roll_vec))

    bpy.ops.object.mode_set(mode="OBJECT")

    # Configure Pose Mode rotation modes to XYZ Euler for deterministic joint control
    for pbone in arm_obj.pose.bones:
        pbone.rotation_mode = "XYZ"

    bpy.context.view_layer.update()
    print(f"[RIG] Created CharacterArmature with {len(arm_data.bones)} bones at {origin_xyz}")
    return arm_obj


def bind_character_to_rig(
    armature_obj: bpy.types.Object,
    parts: Dict[str, bpy.types.Object] = None,
) -> Dict[str, str]:
    """Bind the 13 existing character mesh parts rigidly to their corresponding bones.

    Preserves each part's exact rest-pose world transform while parenting with
    `parent_type = 'BONE'`.
    """
    if parts is None:
        parts = {}
        for part_name in REQUIRED_PARTS:
            obj = bpy.data.objects.get(part_name)
            if obj is None:
                raise RuntimeError(f"Cannot bind missing character part: {part_name}")
            parts[part_name] = obj

    bpy.context.view_layer.update()
    bound_map: Dict[str, str] = {}

    for part_name in REQUIRED_PARTS:
        part_obj = parts.get(part_name) or bpy.data.objects.get(part_name)
        if part_obj is None:
            raise RuntimeError(f"Character part object '{part_name}' not found in scene")

        bone_name = PART_TO_BONE_MAP[part_name]
        bone = armature_obj.data.bones.get(bone_name)
        if bone is None:
            raise RuntimeError(f"Target bone '{bone_name}' for part '{part_name}' not found")

        # Record exact world transform prior to reparenting
        rest_world_matrix = part_obj.matrix_world.copy()

        # Blender's BONE parenting attaches children relative to the bone's tail in rest pose
        bone_rest_tail_world = (
            armature_obj.matrix_world
            @ Matrix.Translation(bone.tail_local - bone.head_local)
            @ bone.matrix_local
        )

        part_obj.parent = armature_obj
        part_obj.parent_type = "BONE"
        part_obj.parent_bone = bone_name
        part_obj.matrix_parent_inverse = bone_rest_tail_world.inverted() @ rest_world_matrix
        part_obj.location = Vector((0.0, 0.0, 0.0))
        part_obj.rotation_euler = (0.0, 0.0, 0.0)
        part_obj.scale = Vector((1.0, 1.0, 1.0))

        bound_map[part_name] = bone_name

    bpy.context.view_layer.update()
    print(f"[RIG] Bound {len(bound_map)} character parts to CharacterArmature bones")
    return bound_map
