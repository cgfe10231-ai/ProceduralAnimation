# Task 10-B-5: Snapshot Data Structure & Immutability Contract

## 1. Immutability & Deep-Value Cloning Contract

To prevent RNA in-place reference leakage (where mutating an array property in Blender RNA simultaneously alters the stored snapshot), `_clone_snapshot_property_value()` strictly decouples snapshot values:

1. **Mathutils Types**: `Vector`, `Euler`, `Quaternion`, `Matrix` are copied via `.copy()`.
2. **RNA Arrays / Sequences**: Python lists, tuples, and Blender RNA collections are converted into immutable `tuple` structures of recursively cloned elements.
3. **ID Datablocks**: Blender ID pointers (`bpy.types.Object`, `bpy.types.Collection`, etc.) are retained by reference, and their C-pointer address (`as_pointer()`) is recorded for identity verification.
4. **Unsupported Properties**: If an essential property fails to be read, an explicit `RuntimeError` is raised with the property name, constraint, and bone context. Silent `except: pass` is strictly prohibited.

## 2. Snapshot Schema Overview

```
snapshot = {
    "character_collection": {
        "existed": bool,
        "name": str,
        "col_ref": bpy.types.Collection,
        "col_ptr": int,
        "children_of_scene": bool,
        "parent_collections": [str, ...],
        "child_collections": [str, ...],
        "object_names": set([str, ...]),
    },
    "controllers": {
        "HandIK.L": {
            "name": "HandIK.L",
            "exists": bool,
            "obj_ref": bpy.types.Object,
            "obj_ptr": int,
            "data_ref": Optional[bpy.types.ID],
            "data_ptr": Optional[int],
            "obj_name": str,
            "type": str,
            "parent": Optional[bpy.types.Object],
            "matrix_parent_inverse": Matrix (4x4),
            "rotation_mode": str,
            "location": Vector (3D),
            "rotation_euler": Euler (3D),
            "rotation_quaternion": Quaternion (4D),
            "rotation_axis_angle": tuple (angle, x, y, z),
            "scale": Vector (3D),
            "empty_display_type": str,
            "empty_display_size": float,
            "collections": [str, ...],
        },
        "HandIK.R": { ... },
        "ElbowPole.L": { ... },
        "ElbowPole.R": { ... },
    },
    "pose_bones": {
        "upper_arm.L": {
            "name": "upper_arm.L",
            "location": Vector,
            "rotation_mode": str,
            "rotation_euler": Euler,
            "rotation_quaternion": Quaternion,
            "rotation_axis_angle": tuple,
            "scale": Vector,
            "matrix_basis": Matrix,
            "lock_ik_x": bool, "lock_ik_y": bool, "lock_ik_z": bool,
            "use_ik_limit_x": bool, "use_ik_limit_y": bool, "use_ik_limit_z": bool,
            "ik_min_x": float, "ik_max_x": float,
            "ik_min_y": float, "ik_max_y": float,
            "ik_min_z": float, "ik_max_z": float,
            "constraints": [
                {
                    "name": str,
                    "type": str,
                    "con_ref": bpy.types.Constraint,
                    "con_ptr": int,
                    "influence": float,
                    "mute": bool,
                    "target": Optional[bpy.types.Object],
                    "subtarget": str,
                    "pole_target": Optional[bpy.types.Object],
                    "pole_subtarget": str,
                    # Type-specific parameters:
                    # (IK: chain_count, use_tail, use_stretch, pole_angle, iterations)
                    # (COPY_ROTATION: target_space, owner_space, mix_mode, use_x/y/z, invert_x/y/z, use_offset)
                    "generic_props": {
                        prop_name: cloned_value (immutable tuple or mathutils copy),
                        ...
                    }
                },
                ...
            ]
        },
        "upper_arm.R": { ... },
        "forearm.L": { ... },
        "forearm.R": { ... },
        "hand.L": { ... },
        "hand.R": { ... },
    }
}
```

## 3. Restoration & Verification Precision

- Transform vectors, scale, and matrices: absolute tolerance `TOL = 1e-5`.
- Quaternion rotations: antipodal tolerance `min(||q1 - q2||, ||q1 + q2||) <= 1e-5`.
- Array elements inside generic properties: element-wise float comparison `abs(a - b) <= 1e-5`.
- Identity pointers: `obj_ptr`, `data_ptr`, `con_ptr` checked when objects remain alive.
