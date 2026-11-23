"""Object-to-Collection link registry recording migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-08)."""

from typing import Any

import bpy


# [INTRODUCED 2026-11-23T21:00:30+08:00]
# NODE: 10-B / L2-08
# FUNCTION: _register_created_collection_link
# PURPOSE: Record an Object -> Collection link mutation created by this transaction in created_collection_links and guard against duplicate pointer-pair entries
# REASON: Migrate TransactionContext relationship-list registration along the normal Blender resource creation chain into Layer 2 while preserving original behavior verbatim
def _register_created_collection_link(
    self: Any,
    col: bpy.types.Collection,
    obj: bpy.types.Object,
) -> None:
    """Register an object-to-collection link mutation created by this transaction."""
    col_ptr = col.as_pointer() if hasattr(col, "as_pointer") else None
    obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None

    for record in self.created_collection_links:
        if record["col_ptr"] == col_ptr and record["obj_ptr"] == obj_ptr:
            return

    self.created_collection_links.append({
        "col_ref": col,
        "col_ptr": col_ptr,
        "col_name": col.name,
        "obj_ref": obj,
        "obj_ptr": obj_ptr,
        "obj_name": obj.name,
    })
