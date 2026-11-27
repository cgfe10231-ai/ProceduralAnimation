"""Independent Blender reopen verifier for TASK 11-A (A16).

Opens a temporary saved .blend file via `blender -b <blend_path> -P verify_footlock_reopen.py -- <spec.json>`,
verifies exact is_locked state and all 7 FOOT_LOCK_METADATA_KEYS presence/values, unrelated custom
properties, controller parent state, and read-only get_foot_support_state() metrics without modifying
or saving the opened file.
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict

import bpy

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.rig.foot_contact import get_foot_support_state
from src.rig.ik import FOOT_LOCK_METADATA_KEYS, IK_TARGET_NAMES, POLE_TARGET_NAMES


def _detach_prop(val: Any) -> Any:
    if hasattr(val, "to_list"):
        return [float(x) for x in val.to_list()]
    if isinstance(val, (list, tuple)):
        return [float(x) for x in val]
    if isinstance(val, bool):
        return bool(val)
    if isinstance(val, (int, float)):
        return float(val)
    return val


def _assert_close_prop(actual: Any, expected: Any, label: str, tol: float = 1e-5) -> None:
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError(f"{label}: expected list len {len(expected)}, got {actual!r}")
        for idx, (a, e) in enumerate(zip(actual, expected)):
            if not math.isclose(float(a), float(e), rel_tol=tol, abs_tol=tol):
                raise AssertionError(f"{label}[{idx}]: {a!r} != {e!r}")
    elif isinstance(expected, bool):
        if type(actual) is not bool or actual != expected:
            raise AssertionError(f"{label}: {actual!r} != {expected!r}")
    elif isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not math.isclose(float(actual), float(expected), rel_tol=tol, abs_tol=tol):
            raise AssertionError(f"{label}: {actual!r} != {expected!r}")
    else:
        if actual != expected:
            raise AssertionError(f"{label}: {actual!r} != {expected!r}")


def main() -> int:
    if "--" not in sys.argv:
        print("[FAIL] Missing spec JSON path after '--'", file=sys.stderr)
        return 1
    spec_path = sys.argv[sys.argv.index("--") + 1]
    with open(spec_path, "r", encoding="utf-8") as fp:
        spec = json.load(fp)

    arm = bpy.data.objects.get("CharacterArmature")
    if arm is None or arm.type != "ARMATURE":
        raise RuntimeError("Reopened blend missing CharacterArmature")

    side_reports: Dict[str, Any] = {}
    for side in ("L", "R"):
        side_spec = spec["sides"][side]
        ik_obj = bpy.data.objects.get(IK_TARGET_NAMES[side])
        pole_obj = bpy.data.objects.get(POLE_TARGET_NAMES[side])
        if ik_obj is None or pole_obj is None:
            raise RuntimeError(f"Reopened blend missing controllers for side {side}")

        actual_locked = bool(ik_obj.get("is_locked", False))
        exp_locked = bool(side_spec["expected_locked"])
        if actual_locked != exp_locked:
            raise AssertionError(f"FootIK.{side} is_locked={actual_locked}, expected={exp_locked}")
        if ik_obj.parent is not None or pole_obj.parent is not None:
            raise AssertionError(f"Controllers for {side} must remain parentless on reopen")

        actual_meta: Dict[str, Any] = {}
        for meta_key in FOOT_LOCK_METADATA_KEYS:
            present = meta_key in ik_obj
            if exp_locked:
                if not present:
                    raise AssertionError(f"Locked FootIK.{side} missing '{meta_key}' after reopen")
                val = _detach_prop(ik_obj[meta_key])
                _assert_close_prop(val, side_spec["expected_metadata"][meta_key], f"FootIK.{side}[{meta_key}]")
                actual_meta[meta_key] = val
            else:
                if present:
                    raise AssertionError(f"Unlocked FootIK.{side} unexpectedly retained '{meta_key}' after reopen")

        for k, exp_v in side_spec.get("expected_unrelated_props", {}).items():
            if k not in ik_obj:
                raise AssertionError(f"FootIK.{side} lost unrelated custom property '{k}' on reopen")
            _assert_close_prop(_detach_prop(ik_obj[k]), exp_v, f"FootIK.{side}[{k}]")

        queried = get_foot_support_state(arm, side)
        if bool(queried["is_locked"]) != exp_locked:
            raise AssertionError(f"get_foot_support_state({side}) is_locked={queried['is_locked']} != {exp_locked}")
        if exp_locked:
            _assert_close_prop(
                [float(v) for v in queried["locked_ankle_world"]],
                side_spec["expected_metadata"]["locked_ankle_world_xyz"],
                f"queried[{side}].locked_ankle_world",
            )
            _assert_close_prop(
                [float(v) for v in queried["contact_world"]],
                side_spec["expected_metadata"]["contact_world_xyz"],
                f"queried[{side}].contact_world",
            )
            _assert_close_prop(
                [float(v) for v in queried["target_rotation_deg"]],
                side_spec["expected_metadata"]["target_rotation_deg"],
                f"queried[{side}].target_rotation_deg",
            )

        side_reports[side] = {
            "is_locked": actual_locked,
            "metadata_keys_present": list(actual_meta.keys()),
            "metadata": actual_meta,
            "queried_controller_drift": round(float(queried["controller_drift"]), 6),
            "queried_ankle_bone_drift": round(float(queried["ankle_bone_drift"]), 6),
        }

    print("REOPEN_VERIFY_RESULT:" + json.dumps({"passed": True, "sides": side_reports}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
