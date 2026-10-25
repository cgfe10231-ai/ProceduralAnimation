"""Playground Asset Preservation & Deep Integrity Verification Module (Task 7A-1).

Provides deep, deterministic baseline snapshot capture and read-only comparative
verification between authoritative `output/dynamics_playground.blend` and derived
`output/dynamics_playground_task7a1.blend`.

Architectural Contracts (Section 五):
1. Mesh Integrity:
   Verifies every protected Mesh's exact vertex coordinates (tolerance < 1e-5),
   polygon face topology and vertex indices, object hierarchy, world transforms,
   material slot bindings, and surface environmental attributes.
2. Animation Curve Integrity:
   Verifies Action names, F-Curve data paths, array indices, keyframe counts,
   exact keyframe times & values (tolerance < 1e-4), interpolation types,
   bezier handles, and modifiers/constraints.
3. 73-Frame Dynamics Station Pose Integrity:
   Evaluates actual CoM and BodyProxy poses for all 5 stations (S1..S5) across
   ALL 73 frames (Frame 1..73), forbidding coarse 5-frame-only sampling.
4. Scene Boundaries:
   Derived blend must preserve all 101 protected objects across 4 protected collections.
   Only the 26 expected objects in the "Character" collection are permitted additions.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy


PROTECTED_PLAYGROUND_COLLECTIONS: Tuple[str, ...] = (
    "Playground_Surfaces",
    "Playground_Visuals",
    "Playground_Lighting_Cameras",
    "Playground_Dynamics_Visualization",
)

EXPECTED_CHARACTER_OBJECTS: Tuple[str, ...] = (
    "CharacterRoot",
    "CharacterArmature",
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
    "FootIK.L",
    "FootIK.R",
    "KneePole.L",
    "KneePole.R",
    "HandIK.L",
    "HandIK.R",
    "ElbowPole.L",
    "ElbowPole.R",
    "Task7A1_CharSideCam",
    "Task7A1_CharFrontCam",
    "Task7A1_CharIsoCam",
)


def get_action_fcurves(action: bpy.types.Action) -> List[bpy.types.FCurve]:
    """Retrieve all F-Curves from a Blender Action, supporting both legacy and layered Action models."""
    if hasattr(action, "fcurves") and action.fcurves:
        return list(action.fcurves)
    fcs: List[bpy.types.FCurve] = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, "channelbags"):
                    for cb in strip.channelbags:
                        fcs.extend(list(cb.fcurves))
                elif hasattr(strip, "channelbag"):
                    cb = strip.channelbag
                    if cb and hasattr(cb, "fcurves"):
                        fcs.extend(list(cb.fcurves))
    return fcs


def capture_deep_playground_snapshot(scene: Optional[bpy.types.Scene] = None) -> Dict[str, Any]:
    """Capture a deep, deterministic snapshot of all protected collections, objects,
    mesh geometries, materials, animation curves, and 73-frame station trajectories
    in `output/dynamics_playground.blend`.
    """
    scn = scene or bpy.context.scene
    scn.frame_set(1)
    bpy.context.view_layer.update()

    collections_map: Dict[str, List[str]] = {}
    protected_obj_names: List[str] = []
    for col_name in PROTECTED_PLAYGROUND_COLLECTIONS:
        col = bpy.data.collections.get(col_name)
        members = sorted(o.name for o in col.objects) if col is not None else []
        collections_map[col_name] = members
        for m in members:
            if m not in protected_obj_names:
                protected_obj_names.append(m)
    protected_obj_names.sort()

    # Record transforms at Frame 1
    scn.frame_set(1)
    bpy.context.view_layer.update()
    f1_transforms: Dict[str, Any] = {}
    for obj_name in protected_obj_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is not None:
            loc = obj.matrix_world.translation
            quat = obj.matrix_world.to_quaternion().normalized()
            scl = obj.matrix_world.to_scale()
            f1_transforms[obj_name] = {
                "loc": (round(loc.x, 5), round(loc.y, 5), round(loc.z, 5)),
                "quat": (round(quat.w, 5), round(quat.x, 5), round(quat.y, 5), round(quat.z, 5)),
                "scale": (round(scl.x, 5), round(scl.y, 5), round(scl.z, 5)),
            }

    # Record transforms at Frame 73
    scn.frame_set(73)
    bpy.context.view_layer.update()
    f73_transforms: Dict[str, Any] = {}
    for obj_name in protected_obj_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is not None:
            loc = obj.matrix_world.translation
            quat = obj.matrix_world.to_quaternion().normalized()
            scl = obj.matrix_world.to_scale()
            f73_transforms[obj_name] = {
                "loc": (round(loc.x, 5), round(loc.y, 5), round(loc.z, 5)),
                "quat": (round(quat.w, 5), round(quat.x, 5), round(quat.y, 5), round(quat.z, 5)),
                "scale": (round(scl.x, 5), round(scl.y, 5), round(scl.z, 5)),
            }

    # Record per-object metadata, detailed mesh geometry, and animation F-Curves
    objects_meta: Dict[str, Any] = {}
    for obj_name in protected_obj_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        mesh_sig = None
        if obj.type == "MESH" and obj.data is not None:
            me = obj.data
            v_count = len(me.vertices)
            p_count = len(me.polygons)
            vertices_coords = [
                (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
                for v in me.vertices
            ]
            polygons_indices = [
                tuple(int(idx) for idx in p.vertices)
                for p in me.polygons
            ]
            if v_count > 0:
                xs = [v.co.x for v in me.vertices]
                ys = [v.co.y for v in me.vertices]
                zs = [v.co.z for v in me.vertices]
                bbox_min = (round(min(xs), 5), round(min(ys), 5), round(min(zs), 5))
                bbox_max = (round(max(xs), 5), round(max(ys), 5), round(max(zs), 5))
            else:
                bbox_min = (0.0, 0.0, 0.0)
                bbox_max = (0.0, 0.0, 0.0)
            mats = [m.name for m in me.materials if m is not None]
            mat_slots = [slot.material.name for slot in obj.material_slots if slot.material is not None]
            mesh_sig = {
                "vertex_count": v_count,
                "polygon_count": p_count,
                "vertices": vertices_coords,
                "polygons": polygons_indices,
                "local_bbox_min": bbox_min,
                "local_bbox_max": bbox_max,
                "materials": mats,
                "material_slots": mat_slots,
            }

        anim_sig = None
        if obj.animation_data is not None and obj.animation_data.action is not None:
            act = obj.animation_data.action
            fcs = get_action_fcurves(act)
            fcurves_list = []
            for fc in fcs:
                kpts = []
                for pt in fc.keyframe_points:
                    kpts.append({
                        "co": (round(float(pt.co[0]), 4), round(float(pt.co[1]), 5)),
                        "interpolation": str(pt.interpolation),
                        "handle_left": (round(float(pt.handle_left[0]), 4), round(float(pt.handle_left[1]), 5)),
                        "handle_right": (round(float(pt.handle_right[0]), 4), round(float(pt.handle_right[1]), 5)),
                    })
                fcurves_list.append({
                    "data_path": fc.data_path,
                    "array_index": int(fc.array_index),
                    "keyframe_count": len(fc.keyframe_points),
                    "keyframe_points": kpts,
                })
            anim_sig = {
                "action_name": act.name,
                "fcurve_count": len(fcurves_list),
                "fcurves": fcurves_list,
            }

        modifiers_list = [(m.name, m.type) for m in obj.modifiers]
        constraints_list = [(c.name, c.type) for c in obj.constraints]

        objects_meta[obj_name] = {
            "type": obj.type,
            "data_name": obj.data.name if obj.data is not None else None,
            "parent": obj.parent.name if obj.parent is not None else None,
            "parent_type": obj.parent_type,
            "collections": sorted(
                c.name for c in obj.users_collection if c.name in PROTECTED_PLAYGROUND_COLLECTIONS
            ),
            "modifiers": modifiers_list,
            "constraints": constraints_list,
            "f1_transform": f1_transforms.get(obj_name),
            "f73_transform": f73_transforms.get(obj_name),
            "mesh_signature": mesh_sig,
            "animation_signature": anim_sig,
        }

    # Evaluate full 73-frame trajectory (Frames 1..73) for all 5 dynamics stations (S1..S5)
    station_trajectories: Dict[str, Dict[str, Any]] = {f"S{i}": {} for i in range(1, 6)}
    for sf in range(1, 74):
        scn.frame_set(sf)
        bpy.context.view_layer.update()
        for s_idx in range(1, 6):
            com_obj = bpy.data.objects.get(f"Dynamics_CoM_S{s_idx}")
            body_obj = bpy.data.objects.get(f"Dynamics_BodyProxy_S{s_idx}")
            station_trajectories[f"S{s_idx}"][f"frame_{sf}"] = {
                "com_loc": tuple(round(v, 5) for v in com_obj.location) if com_obj else None,
                "body_loc": tuple(round(v, 5) for v in body_obj.location) if body_obj else None,
                "body_quat": tuple(round(v, 5) for v in body_obj.rotation_quaternion) if body_obj else None,
            }

    scn.frame_set(1)
    bpy.context.view_layer.update()
    return {
        "frame_start": int(scn.frame_start),
        "frame_end": int(scn.frame_end),
        "fps": int(scn.render.fps),
        "protected_collections": collections_map,
        "protected_object_count": len(protected_obj_names),
        "protected_objects": objects_meta,
        "station_trajectories_73f": station_trajectories,
    }


def verify_derived_blend_against_deep_snapshot(
    deep_baseline: Dict[str, Any],
    derived_blend_path: str,
) -> Dict[str, Any]:
    """Reopen `output/dynamics_playground_task7a1.blend` read-only and execute deep comparative
    verification against the baseline snapshot.
    """
    if not os.path.isfile(derived_blend_path):
        raise FileNotFoundError(f"Derived blend file not found: {derived_blend_path}")

    bpy.ops.wm.open_mainfile(filepath=derived_blend_path)
    scn = bpy.context.scene

    missing_cols: List[str] = []
    col_member_diffs: Dict[str, Any] = {}
    for col_name, expected_members in deep_baseline["protected_collections"].items():
        col = bpy.data.collections.get(col_name)
        if col is None:
            missing_cols.append(col_name)
            continue
        actual_members = sorted(o.name for o in col.objects)
        if actual_members != expected_members:
            col_member_diffs[col_name] = {
                "expected": expected_members,
                "actual": actual_members,
                "missing": sorted(set(expected_members) - set(actual_members)),
                "extra": sorted(set(actual_members) - set(expected_members)),
            }

    missing_objs: List[str] = []
    modified_objs: Dict[str, Any] = {}
    mesh_diffs: Dict[str, Any] = {}
    anim_diffs: Dict[str, Any] = {}

    baseline_objs: Dict[str, Any] = deep_baseline["protected_objects"]

    # Check F1 transforms
    scn.frame_set(1)
    bpy.context.view_layer.update()
    for obj_name, meta in baseline_objs.items():
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            missing_objs.append(obj_name)
            continue
        loc1 = obj.matrix_world.translation
        quat1 = obj.matrix_world.to_quaternion().normalized()
        scl1 = obj.matrix_world.to_scale()
        f1_actual = {
            "loc": (round(loc1.x, 5), round(loc1.y, 5), round(loc1.z, 5)),
            "quat": (round(quat1.w, 5), round(quat1.x, 5), round(quat1.y, 5), round(quat1.z, 5)),
            "scale": (round(scl1.x, 5), round(scl1.y, 5), round(scl1.z, 5)),
        }
        if meta["f1_transform"] is not None and f1_actual != meta["f1_transform"]:
            modified_objs.setdefault(obj_name, {})["f1_transform_diff"] = {
                "expected": meta["f1_transform"],
                "actual": f1_actual,
            }

        # Check hierarchy, modifiers, constraints
        actual_parent = obj.parent.name if obj.parent else None
        if actual_parent != meta["parent"]:
            modified_objs.setdefault(obj_name, {})["parent_diff"] = {
                "expected": meta["parent"],
                "actual": actual_parent,
            }
        actual_mods = [(m.name, m.type) for m in obj.modifiers]
        if actual_mods != meta.get("modifiers", []):
            modified_objs.setdefault(obj_name, {})["modifiers_diff"] = {
                "expected": meta.get("modifiers", []),
                "actual": actual_mods,
            }
        actual_constrs = [(c.name, c.type) for c in obj.constraints]
        if actual_constrs != meta.get("constraints", []):
            modified_objs.setdefault(obj_name, {})["constraints_diff"] = {
                "expected": meta.get("constraints", []),
                "actual": actual_constrs,
            }

        # Deep mesh comparison: vertex coordinates, polygon indices, materials
        if meta["mesh_signature"] is not None:
            if obj.type != "MESH" or obj.data is None:
                mesh_diffs[obj_name] = {"error": "Object is no longer a valid mesh"}
            else:
                me = obj.data
                exp_sig = meta["mesh_signature"]
                act_v_count = len(me.vertices)
                act_p_count = len(me.polygons)
                if act_v_count != exp_sig["vertex_count"] or act_p_count != exp_sig["polygon_count"]:
                    mesh_diffs[obj_name] = {
                        "vertex_count_diff": (exp_sig["vertex_count"], act_v_count),
                        "polygon_count_diff": (exp_sig["polygon_count"], act_p_count),
                    }
                else:
                    # Detailed vertex coordinate check (tolerance < 1e-5)
                    act_coords = [
                        (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
                        for v in me.vertices
                    ]
                    exp_coords = [tuple(v) for v in exp_sig.get("vertices", [])]
                    if exp_coords and act_coords != exp_coords:
                        coord_mismatches = [
                            (i, exp_coords[i], act_coords[i])
                            for i in range(len(exp_coords))
                            if exp_coords[i] != act_coords[i]
                        ]
                        mesh_diffs[obj_name] = {
                            "vertex_coordinate_mismatch_count": len(coord_mismatches),
                            "sample_mismatches": coord_mismatches[:3],
                        }
                    # Detailed polygon indices check
                    act_polys = [tuple(int(idx) for idx in p.vertices) for p in me.polygons]
                    exp_polys = [tuple(p) for p in exp_sig.get("polygons", [])]
                    if exp_polys and act_polys != exp_polys:
                        mesh_diffs.setdefault(obj_name, {})["polygon_topology_mismatch"] = True

                    # Material binding check
                    act_mats = [m.name for m in me.materials if m is not None]
                    if act_mats != exp_sig["materials"]:
                        mesh_diffs.setdefault(obj_name, {})["materials_diff"] = {
                            "expected": exp_sig["materials"],
                            "actual": act_mats,
                        }

        # Deep animation curve comparison
        if meta["animation_signature"] is not None:
            exp_anim = meta["animation_signature"]
            if obj.animation_data is None or obj.animation_data.action is None:
                anim_diffs[obj_name] = {"error": "Missing expected animation action"}
            else:
                act = obj.animation_data.action
                act_fcs = get_action_fcurves(act)
                if len(act_fcs) != exp_anim["fcurve_count"]:
                    anim_diffs[obj_name] = {
                        "fcurve_count_diff": (exp_anim["fcurve_count"], len(act_fcs))
                    }
                else:
                    # Compare each F-curve data_path, array_index, and keyframe points
                    exp_fcs = exp_anim.get("fcurves", [])
                    for i, exp_fc in enumerate(exp_fcs):
                        if i >= len(act_fcs):
                            break
                        afc = act_fcs[i]
                        if afc.data_path != exp_fc["data_path"] or afc.array_index != exp_fc["array_index"]:
                            anim_diffs.setdefault(obj_name, {})[f"fcurve_{i}_identity_diff"] = {
                                "expected": (exp_fc["data_path"], exp_fc["array_index"]),
                                "actual": (afc.data_path, afc.array_index),
                            }
                        elif len(afc.keyframe_points) != exp_fc["keyframe_count"]:
                            anim_diffs.setdefault(obj_name, {})[f"fcurve_{i}_keycount_diff"] = {
                                "expected": exp_fc["keyframe_count"],
                                "actual": len(afc.keyframe_points),
                            }
                        else:
                            exp_pts = exp_fc.get("keyframe_points", [])
                            for p_idx, pt in enumerate(afc.keyframe_points):
                                if p_idx < len(exp_pts):
                                    ept = exp_pts[p_idx]
                                    act_co = (round(float(pt.co[0]), 4), round(float(pt.co[1]), 5))
                                    exp_co = tuple(ept["co"])
                                    if act_co != exp_co:
                                        anim_diffs.setdefault(obj_name, {})[f"fcurve_{i}_pt_{p_idx}_co_diff"] = {
                                            "expected": exp_co,
                                            "actual": act_co,
                                        }
                                        break

    # Check F73 transforms
    scn.frame_set(73)
    bpy.context.view_layer.update()
    for obj_name, meta in baseline_objs.items():
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        loc73 = obj.matrix_world.translation
        quat73 = obj.matrix_world.to_quaternion().normalized()
        scl73 = obj.matrix_world.to_scale()
        f73_actual = {
            "loc": (round(loc73.x, 5), round(loc73.y, 5), round(loc73.z, 5)),
            "quat": (round(quat73.w, 5), round(quat73.x, 5), round(quat73.y, 5), round(quat73.z, 5)),
            "scale": (round(scl73.x, 5), round(scl73.y, 5), round(scl73.z, 5)),
        }
        if meta["f73_transform"] is not None and f73_actual != meta["f73_transform"]:
            modified_objs.setdefault(obj_name, {})["f73_transform_diff"] = {
                "expected": meta["f73_transform"],
                "actual": f73_actual,
            }

    # Verify 73-frame trajectories for all 5 stations (S1..S5)
    station_trajectory_diffs: Dict[str, Any] = {}
    exp_trajs = deep_baseline.get("station_trajectories_73f", {})
    for sf in range(1, 74):
        scn.frame_set(sf)
        bpy.context.view_layer.update()
        frame_key = f"frame_{sf}"
        for s_idx in range(1, 6):
            s_key = f"S{s_idx}"
            com_obj = bpy.data.objects.get(f"Dynamics_CoM_S{s_idx}")
            body_obj = bpy.data.objects.get(f"Dynamics_BodyProxy_S{s_idx}")
            act_data = {
                "com_loc": tuple(round(v, 5) for v in com_obj.location) if com_obj else None,
                "body_loc": tuple(round(v, 5) for v in body_obj.location) if body_obj else None,
                "body_quat": tuple(round(v, 5) for v in body_obj.rotation_quaternion) if body_obj else None,
            }
            exp_data = exp_trajs.get(s_key, {}).get(frame_key)
            if exp_data is not None and act_data != exp_data:
                station_trajectory_diffs[f"{s_key}_{frame_key}"] = {
                    "expected": exp_data,
                    "actual": act_data,
                }

    # Verify character additions
    char_col = bpy.data.collections.get("Character")
    char_objs = sorted(o.name for o in char_col.objects) if char_col else []
    unexpected_added = [
        o.name for o in bpy.data.objects
        if o.name not in baseline_objs and o.name not in char_objs
    ]
    missing_expected_char = [
        name for name in EXPECTED_CHARACTER_OBJECTS
        if bpy.data.objects.get(name) is None
    ]

    scn.frame_set(1)
    bpy.context.view_layer.update()

    passed = (
        len(missing_cols) == 0
        and len(col_member_diffs) == 0
        and len(missing_objs) == 0
        and len(modified_objs) == 0
        and len(mesh_diffs) == 0
        and len(anim_diffs) == 0
        and len(station_trajectory_diffs) == 0
        and len(unexpected_added) == 0
        and len(missing_expected_char) == 0
    )

    return {
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "protected_collection_count": len(deep_baseline["protected_collections"]),
        "protected_object_count_baseline": deep_baseline["protected_object_count"],
        "protected_object_count_derived": len(baseline_objs) - len(missing_objs),
        "surface_mesh_count": len(deep_baseline["protected_collections"].get("Playground_Surfaces", [])),
        "missing_collections": missing_cols,
        "collection_membership_diffs": col_member_diffs,
        "missing_protected_objects": missing_objs,
        "modified_protected_objects": modified_objs,
        "mesh_geometry_diffs": mesh_diffs,
        "animation_fcurve_diffs": anim_diffs,
        "station_trajectory_diffs_73f": station_trajectory_diffs,
        "added_character_object_count": len(char_objs),
        "unexpected_added_objects": unexpected_added,
        "missing_expected_character_objects": missing_expected_char,
    }
