"""Task 10-d-3 standalone complete verification for T15 (68 subcases untruncated)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

EVIDENCE_DIR = Path(__file__).resolve().parent
if str(EVIDENCE_DIR) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_DIR))

from verify_upper_limb_segment import _extract_production_symbols  # noqa: E402

RESULTS_PATH = EVIDENCE_DIR / "t15_complete.json"


def main() -> int:
    ns, baseline = _extract_production_symbols()
    UpperLimbSegment = ns["UpperLimbSegment"]
    _validate_upper_limb_vector = ns["_validate_upper_limb_vector"]
    _evaluate_upper_limb_segment = ns["_evaluate_upper_limb_segment"]

    subcases: List[Dict[str, Any]] = []
    status = "PASS"
    error_text = None

    try:
        # T15 — Vector & root_yaw rejection (exact 68 assertions from verify_upper_limb_segment.py)
        bad_vecs: List[Tuple[str, Any, type]] = [
            ("list_not_tuple", [0.0, 1.0, 2.0], TypeError),
            ("len_2", (0.0, 1.0), ValueError),
            ("len_4", (0.0, 1.0, 2.0, 3.0), ValueError),
            ("bool_comp", (True, 0.0, 0.0), TypeError),
            ("str_comp", ("0.0", 0.0, 0.0), TypeError),
            ("none_vec", None, TypeError),
            ("nan_comp", (0.0, float("nan"), 0.0), ValueError),
            ("pos_inf_comp", (float("inf"), 0.0, 0.0), ValueError),
            ("neg_inf_comp", (0.0, 0.0, float("-inf")), ValueError),
            ("huge_int_comp", (0.0, 10**400, 0.0), ValueError),
        ]
        for label, bad_v, exp_cls in bad_vecs:
            # Direct _validate_upper_limb_vector
            raised = None
            try:
                _validate_upper_limb_vector(bad_v, "test_vec")
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, ("direct", label, raised)
            subcases.append({"target": "_validate_upper_limb_vector", "case": label, "expected": exp_cls.__name__, "actual": raised})

        # Via _evaluate_upper_limb_segment across FK, wrist, rotation, pole, root_position
        ok_rot = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        ok_v = (0.0, 0.0, 1.0)
        for label, bad_v, exp_cls in bad_vecs:
            calls: List[Tuple[str, Any, Any]] = [
                ("wrist_start_xyz", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=bad_v, wrist_end_xyz=ok_v), ok_v),
                ("rotation_start_deg", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v, rotation_start_deg=bad_v, rotation_end_deg=ok_v), ok_v),
                ("pole_end_xyz", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v, pole_start_xyz=ok_v, pole_end_xyz=bad_v), ok_v),
                ("fk_start_deg_0", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=(bad_v, ok_v, ok_v), fk_end_deg=ok_rot), ok_v),
                ("root_position", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v), bad_v),
            ]
            for field_name, seg, rp in calls:
                raised = None
                try:
                    _evaluate_upper_limb_segment(seg, "L", 0.5, rp, 0.0)
                except Exception as exc:
                    raised = type(exc).__name__
                expected_name = "ValueError" if (bad_v is None and field_name != "root_position" and field_name != "fk_start_deg_0") else exp_cls.__name__
                assert raised == expected_name, (field_name, label, expected_name, raised)
                subcases.append({"target": field_name, "case": label, "expected": expected_name, "actual": raised})

        # root_yaw_deg checks
        ok_seg = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v)
        bad_yaws: List[Tuple[str, Any, type]] = [
            ("yaw_bool", True, TypeError),
            ("yaw_str", "90", TypeError),
            ("yaw_none", None, TypeError),
            ("yaw_list", [0.0], TypeError),
            ("yaw_nan", float("nan"), ValueError),
            ("yaw_pos_inf", float("inf"), ValueError),
            ("yaw_neg_inf", float("-inf"), ValueError),
            ("yaw_huge_int", 10**400, ValueError),
        ]
        for label, bad_y, exp_cls in bad_yaws:
            raised = None
            try:
                _evaluate_upper_limb_segment(ok_seg, "L", 0.5, ok_v, bad_y)  # type: ignore[arg-type]
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, (label, raised)
            subcases.append({"target": "root_yaw_deg", "case": label, "expected": exp_cls.__name__, "actual": raised})

        assert len(subcases) == 68, len(subcases)
        print(f"[PASS] T15: 向量输入与 Root yaw 拒绝 ({len(subcases)}/68 subcases)", flush=True)
    except Exception as exc:
        status = "FAIL"
        error_text = f"{type(exc).__name__}: {exc}"
        print(f"[FAIL] T15 -> {error_text}", flush=True)

    exit_code = 0 if status == "PASS" and len(subcases) == 68 else 1
    payload = {
        "task": "TASK 10-d-3 — T15 证据补全",
        "command": " ".join([sys.executable, "-B", "docs/evidence/10-d/10-d-3/verify_t15_completion.py"]),
        "exit_code": exit_code,
        "source_baseline": baseline,
        "test": {
            "id": "T15",
            "title": "向量输入与 Root yaw 拒绝",
            "status": status,
            "subcases_count": len(subcases),
            "subcases": subcases,
            **({"error": error_text} if error_text is not None else {}),
        },
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SUMMARY: T15={status} subcases={len(subcases)} exit_code={exit_code}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
