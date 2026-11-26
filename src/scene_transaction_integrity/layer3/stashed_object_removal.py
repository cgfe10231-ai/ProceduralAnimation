"""Stashed doomed Object physical removal and post-delete verification migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L6-01)."""

from typing import Any

import bpy


# [INTRODUCED 2026-11-24T15:56:00+08:00]
# NODE: 10-B / L6-01
# FUNCTION: _remove_stashed_object_and_verify
# PURPOSE: 按原指针优先/引用备用顺序定位废弃 Object，执行 do_unlink=True 删除并二次核验其已从 bpy.data.objects 移除
# REASON: 将 Blender 物理 Object 删除与删后存在性核验从 arm_ik.py 迁入 Layer 3，严禁 Layer 3 反向调用 Layer 6
def _remove_stashed_object_and_verify(
    obj_ref: Any,
    obj_ptr: Any,
) -> bool:
    """Execute the existing stashed Object removal and absence check."""
    target_obj = None
    for o in bpy.data.objects:
        try:
            if obj_ptr and o.as_pointer() == obj_ptr:
                target_obj = o
                break
            elif obj_ref is not None and o == obj_ref:
                target_obj = o
                break
        except ReferenceError:
            continue

    if target_obj is not None:
        bpy.data.objects.remove(target_obj, do_unlink=True)
        still_exists = any(
            (obj_ptr and o.as_pointer() == obj_ptr)
            for o in bpy.data.objects
        )
        return not still_exists

    return True
