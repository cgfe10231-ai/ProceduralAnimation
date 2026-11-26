"""Read-only collection relationship queries migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3)."""

from typing import Optional, Set

import bpy


def _is_object_linked_to_collection_by_identity(
    collection: bpy.types.Collection,
    obj_ref: Optional[bpy.types.Object],
    expected_obj_ptr: Optional[int],
) -> bool:
    """Check whether an object is currently linked to a collection by reference and pointer identity."""
    if collection is None:
        return False
    if obj_ref is None and expected_obj_ptr is None:
        return False

    if obj_ref is not None:
        try:
            ref_ptr = obj_ref.as_pointer()
        except ReferenceError:
            return False
        if expected_obj_ptr is not None and ref_ptr != expected_obj_ptr:
            return False
        target_ptr = expected_obj_ptr if expected_obj_ptr is not None else ref_ptr
    else:
        target_ptr = expected_obj_ptr

    try:
        for candidate in collection.objects:
            try:
                if candidate.as_pointer() != target_ptr:
                    continue
                if obj_ref is None or candidate == obj_ref:
                    return True
            except ReferenceError:
                continue
    except ReferenceError:
        return False

    return False


def _is_child_collection_linked_by_identity(
    parent: bpy.types.Collection,
    child: bpy.types.Collection,
    child_ptr: Optional[int] = None,
) -> bool:
    """Verify whether child is linked under parent by identity pointer and reference."""
    try:
        if child_ptr is None and hasattr(child, "as_pointer"):
            child_ptr = child.as_pointer()
        for c in parent.children:
            try:
                if c == child or (child_ptr is not None and c.as_pointer() == child_ptr):
                    return True
            except ReferenceError:
                continue
    except (ReferenceError, Exception):
        return False
    return False


def _is_collection_descendant_of(
    candidate_child: bpy.types.Collection,
    candidate_ancestor: bpy.types.Collection,
    visited: Optional[Set[int]] = None,
) -> bool:
    """Check if candidate_ancestor is equal to or an ancestor of candidate_child."""
    if visited is None:
        visited = set()
    anc_ptr = candidate_ancestor.as_pointer() if hasattr(candidate_ancestor, "as_pointer") else None
    ch_ptr = candidate_child.as_pointer() if hasattr(candidate_child, "as_pointer") else None
    if anc_ptr is not None and ch_ptr is not None and anc_ptr == ch_ptr:
        return True
    if anc_ptr in visited:
        return False
    if anc_ptr is not None:
        visited.add(anc_ptr)
    for sub in candidate_ancestor.children:
        if _is_collection_descendant_of(candidate_child, sub, visited):
            return True
    return False


def _find_collection_by_name(col_name: str) -> Optional[bpy.types.Collection]:
    """Resolve a collection by name across scene master collections and user collections."""
    if bpy.context.scene and bpy.context.scene.collection.name == col_name:
        return bpy.context.scene.collection
    for scene in bpy.data.scenes:
        if scene.collection.name == col_name:
            return scene.collection
    return bpy.data.collections.get(col_name)
