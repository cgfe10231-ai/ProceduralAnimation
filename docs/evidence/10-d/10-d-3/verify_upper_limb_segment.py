"""Task 10-d-3 targeted verification for UpperLimbSegment and FK/IK target evaluation."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[4]
EVIDENCE_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVIDENCE_DIR / "results.json"

EXTRACTION_SPEC: List[Tuple[str, str, str]] = [
    ("src/motion/contact_model.py", "class", "ContactType"),
    ("src/motion/framework.py", "def", "right_unit_vector_from_yaw"),
    ("src/motion/framework.py", "def", "forward_unit_vector_from_yaw"),
    ("src/motion/framework.py", "def", "root_local_to_world_vector"),
    ("src/motion/kinematic_bridge.py", "class", "PlannedHandTarget"),
    ("src/motion/terrain_walk.py", "class", "UpperLimbSegment"),
    ("src/motion/terrain_walk.py", "def", "_evaluate_upper_limb_progress"),
    ("src/motion/terrain_walk.py", "def", "_validate_upper_limb_vector"),
    ("src/motion/terrain_walk.py", "def", "_evaluate_upper_limb_segment"),
]


def _extract_production_symbols() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    file_cache: Dict[str, Tuple[str, ast.Module, str]] = {}
    namespace: Dict[str, Any] = {
        "Any": Any,
        "Dict": Dict,
        "Enum": Enum,
        "List": List,
        "Optional": Optional,
        "Tuple": Tuple,
        "dataclass": dataclass,
        "math": math,
    }
    extracted_meta: List[Dict[str, Any]] = []

    for rel_path, kind, name in EXTRACTION_SPEC:
        if rel_path not in file_cache:
            abs_path = REPO_ROOT / rel_path
            raw_bytes = abs_path.read_bytes()
            text = raw_bytes.decode("utf-8")
            tree = ast.parse(text, filename=str(abs_path))
            blob = subprocess.check_output(
                ["git", "hash-object", rel_path], cwd=REPO_ROOT, text=True
            ).strip()
            file_cache[rel_path] = (text, tree, blob)

        text, tree, blob = file_cache[rel_path]
        node_type = ast.ClassDef if kind == "class" else ast.FunctionDef
        target_node = None
        for node in tree.body:
            if isinstance(node, node_type) and node.name == name:
                target_node = node
                break
        if target_node is None:
            raise RuntimeError(f"Symbol {name} ({kind}) not found in {rel_path}")

        decorators = getattr(target_node, "decorator_list", [])
        start_line = min([target_node.lineno] + [d.lineno for d in decorators])
        lines = text.splitlines()
        src_segment = "\n".join(lines[start_line - 1 : target_node.end_lineno])

        seg_sha256 = hashlib.sha256(src_segment.encode("utf-8")).hexdigest()
        code = compile(src_segment, str(REPO_ROOT / rel_path), "exec")
        exec(code, namespace, namespace)

        extracted_meta.append(
            {
                "symbol": name,
                "kind": kind,
                "source_file": rel_path,
                "source_blob": blob,
                "lines": [start_line, target_node.end_lineno],
                "sha256": seg_sha256,
            }
        )

    git_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True
    ).strip()
    git_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()

    baseline = {
        "branch": git_branch,
        "head": git_head,
        "file_blobs": {k: v[2] for k, v in file_cache.items()},
        "extracted_definitions": extracted_meta,
    }
    return namespace, baseline


def _vec_max_err(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def main() -> int:
    ns, baseline = _extract_production_symbols()
    ContactType = ns["ContactType"]
    root_local_to_world_vector = ns["root_local_to_world_vector"]
    PlannedHandTarget = ns["PlannedHandTarget"]
    UpperLimbSegment = ns["UpperLimbSegment"]
    _evaluate_upper_limb_progress = ns["_evaluate_upper_limb_progress"]
    _validate_upper_limb_vector = ns["_validate_upper_limb_vector"]
    _evaluate_upper_limb_segment = ns["_evaluate_upper_limb_segment"]

    TOL = 1e-12
    records: List[Dict[str, Any]] = []

    def run_test(test_id: str, title: str, body: Callable[[], Dict[str, Any]]) -> None:
        try:
            detail = body()
            records.append(
                {
                    "id": test_id,
                    "title": title,
                    "status": "PASS",
                    **detail,
                }
            )
            print(f"[PASS] {test_id}: {title}", flush=True)
        except Exception as exc:
            records.append(
                {
                    "id": test_id,
                    "title": title,
                    "status": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[FAIL] {test_id}: {title} -> {type(exc).__name__}: {exc}", flush=True)

    # T01 — FK time boundaries
    def test_t01() -> Dict[str, Any]:
        s_rot = ((0.0, 0.0, 0.0), (10.0, -20.0, 30.0), (-5.0, 15.0, -25.0))
        e_rot = ((20.0, -40.0, 60.0), (50.0, 20.0, -10.0), (15.0, -5.0, 55.0))
        seg = UpperLimbSegment(
            mode="FK",
            start_time_sec=2.0,
            duration_sec=4.0,
            fk_start_deg=s_rot,
            fk_end_deg=e_rot,
        )
        times = [0.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5]
        subcases = []
        max_err = 0.0
        for t in times:
            _, h = _evaluate_upper_limb_progress(t, 2.0, 4.0)
            target, fk = _evaluate_upper_limb_segment(seg, "L", t, (0.0, 0.0, 0.0), 0.0)
            assert target is None, target
            expected = {
                f"{b}.L": [
                    (1.0 - h) * sv[j] + h * ev[j] for j in range(3)
                ]
                for b, sv, ev in zip(("upper_arm", "forearm", "hand"), s_rot, e_rot)
            }
            actual = {k: list(v) for k, v in fk.items()}
            err = max(_vec_max_err(tuple(expected[k]), fk[k]) for k in expected)
            max_err = max(max_err, err)
            assert err <= TOL, (t, expected, actual, err)
            subcases.append(
                {
                    "input_time_sec": t,
                    "h": h,
                    "expected": expected,
                    "actual": actual,
                    "max_abs_err": err,
                }
            )
        return {"max_abs_err": max_err, "tolerance": TOL, "subcases": subcases}

    # T02 — FK independent 3-axis interpolation across all 9 components
    def test_t02() -> Dict[str, Any]:
        s_rot = ((10.0, -20.0, 30.0), (-40.0, 50.0, -60.0), (7.0, -8.0, 9.0))
        e_rot = ((30.0, 20.0, -10.0), (40.0, -30.0, 20.0), (-13.0, 32.0, 49.0))
        seg = UpperLimbSegment(
            mode="FK",
            start_time_sec=1.0,
            duration_sec=4.0,
            fk_start_deg=s_rot,
            fk_end_deg=e_rot,
        )
        t = 2.0  # u=0.25, h=0.103515625
        _, h = _evaluate_upper_limb_progress(t, 1.0, 4.0)
        target, fk = _evaluate_upper_limb_segment(seg, "R", t, (1.0, 2.0, 3.0), 45.0)
        assert target is None
        components = []
        max_err = 0.0
        for b, sv, ev in zip(("upper_arm", "forearm", "hand"), s_rot, e_rot):
            key = f"{b}.R"
            for axis_idx, axis_name in enumerate(("x", "y", "z")):
                exp_v = (1.0 - h) * sv[axis_idx] + h * ev[axis_idx]
                act_v = fk[key][axis_idx]
                err = abs(act_v - exp_v)
                max_err = max(max_err, err)
                assert err <= TOL, (key, axis_name, exp_v, act_v, err)
                components.append(
                    {
                        "bone": key,
                        "axis": axis_name,
                        "input_start": sv[axis_idx],
                        "input_end": ev[axis_idx],
                        "expected": exp_v,
                        "actual": act_v,
                        "abs_err": err,
                    }
                )
        return {"h": h, "max_abs_err": max_err, "components_count": len(components), "components": components}

    # T03 — Left/right bone dict isolation
    def test_t03() -> Dict[str, Any]:
        s_rot = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0))
        e_rot = ((11.0, 12.0, 13.0), (14.0, 15.0, 16.0), (17.0, 18.0, 19.0))
        seg = UpperLimbSegment("FK", 0.0, 2.0, fk_start_deg=s_rot, fk_end_deg=e_rot)
        tl, fk_l = _evaluate_upper_limb_segment(seg, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
        tr, fk_r = _evaluate_upper_limb_segment(seg, "R", 1.0, (0.0, 0.0, 0.0), 0.0)
        assert tl is None and tr is None
        exp_l = ["upper_arm.L", "forearm.L", "hand.L"]
        exp_r = ["upper_arm.R", "forearm.R", "hand.R"]
        assert sorted(fk_l.keys()) == sorted(exp_l), fk_l.keys()
        assert sorted(fk_r.keys()) == sorted(exp_r), fk_r.keys()
        assert not any(k.endswith(".R") for k in fk_l)
        assert not any(k.endswith(".L") for k in fk_r)
        return {
            "left": {"expected_keys": exp_l, "actual_keys": list(fk_l.keys())},
            "right": {"expected_keys": exp_r, "actual_keys": list(fk_r.keys())},
        }

    # T04 — IK world-space interpolation & invariance to root position/yaw
    def test_t04() -> Dict[str, Any]:
        ws = (0.3, -0.4, 1.1)
        we = (0.7, 0.8, 1.9)
        seg = UpperLimbSegment(
            mode="IK",
            start_time_sec=2.0,
            duration_sec=4.0,
            wrist_start_xyz=ws,
            wrist_end_xyz=we,
            position_space="WORLD",
        )
        subcases = []
        max_err = 0.0
        for t in (2.0, 3.0, 4.0, 6.0):
            _, h = _evaluate_upper_limb_progress(t, 2.0, 4.0)
            exp = tuple((1.0 - h) * ws[i] + h * we[i] for i in range(3))
            t1, fk1 = _evaluate_upper_limb_segment(seg, "L", t, (0.0, 0.0, 0.0), 0.0)
            t2, fk2 = _evaluate_upper_limb_segment(seg, "L", t, (100.0, -50.0, 25.0), 137.0)
            assert fk1 == {} and fk2 == {} and t1 is not None and t2 is not None
            err1 = _vec_max_err(t1.world_xyz, exp)
            err2 = _vec_max_err(t2.world_xyz, exp)
            assert err1 <= TOL and t1.world_xyz == t2.world_xyz
            max_err = max(max_err, err1, err2)
            subcases.append(
                {
                    "input_time_sec": t,
                    "expected_world_xyz": list(exp),
                    "actual_root0": list(t1.world_xyz),
                    "actual_root_shifted": list(t2.world_xyz),
                    "abs_err": err1,
                }
            )
        return {"max_abs_err": max_err, "subcases": subcases}

    # T05 — IK ROOT_LOCAL rotation + translation composition
    def test_t05() -> Dict[str, Any]:
        ls = (0.2, 0.5, 0.3)
        le = (-0.4, 0.8, 0.9)
        root_pos = (5.0, -3.0, 1.2)
        root_yaw = 37.0
        seg = UpperLimbSegment(
            mode="IK",
            start_time_sec=1.0,
            duration_sec=2.0,
            wrist_start_xyz=ls,
            wrist_end_xyz=le,
            position_space="ROOT_LOCAL",
        )
        subcases = []
        max_err = 0.0
        for t in (1.0, 1.5, 2.0, 3.0):
            _, h = _evaluate_upper_limb_progress(t, 1.0, 2.0)
            local_interp = tuple((1.0 - h) * ls[i] + h * le[i] for i in range(3))
            wv = root_local_to_world_vector(local_interp, root_yaw)
            exp = tuple(root_pos[i] + wv[i] for i in range(3))
            target, fk = _evaluate_upper_limb_segment(seg, "R", t, root_pos, root_yaw)
            assert fk == {} and target is not None
            err = _vec_max_err(target.world_xyz, exp)
            max_err = max(max_err, err)
            assert err <= TOL, (t, exp, target.world_xyz, err)
            subcases.append(
                {
                    "input_time_sec": t,
                    "local_interp": list(local_interp),
                    "expected_world_xyz": list(exp),
                    "actual_world_xyz": list(target.world_xyz),
                    "abs_err": err,
                }
            )
        return {"root_position": list(root_pos), "root_yaw_deg": root_yaw, "max_abs_err": max_err, "subcases": subcases}

    # T06 — Root yaw math contract at 0, 90, -90, 180 deg
    def test_t06() -> Dict[str, Any]:
        local_pt = (1.0, 2.0, 3.0)
        root_pt = (10.0, 20.0, 30.0)
        seg = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=1.0,
            wrist_start_xyz=local_pt,
            wrist_end_xyz=local_pt,
            position_space="ROOT_LOCAL",
        )
        cases = [
            (0.0, (11.0, 22.0, 33.0)),
            (90.0, (8.0, 21.0, 33.0)),
            (-90.0, (12.0, 19.0, 33.0)),
            (180.0, (9.0, 18.0, 33.0)),
        ]
        subcases = []
        max_err = 0.0
        for yaw, exp in cases:
            target, _ = _evaluate_upper_limb_segment(seg, "L", 0.5, root_pt, yaw)
            assert target is not None
            err = _vec_max_err(target.world_xyz, exp)
            max_err = max(max_err, err)
            assert err <= TOL, (yaw, exp, target.world_xyz, err)
            subcases.append(
                {
                    "input_local": list(local_pt),
                    "input_root": list(root_pt),
                    "input_yaw_deg": yaw,
                    "expected_world_xyz": list(exp),
                    "actual_world_xyz": list(target.world_xyz),
                    "abs_err": err,
                }
            )
        return {"max_abs_err": max_err, "subcases": subcases}

    # T07 — Counterfactual Root translation delta
    def test_t07() -> Dict[str, Any]:
        seg = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.2, 0.4, 0.6),
            wrist_end_xyz=(0.6, 0.8, 1.0),
            pole_start_xyz=(-0.1, -0.3, 0.4),
            pole_end_xyz=(-0.3, -0.5, 0.8),
            position_space="ROOT_LOCAL",
        )
        r1 = (1.5, -2.0, 0.5)
        r2 = (11.5, 4.0, -3.5)
        delta_root = tuple(r2[i] - r1[i] for i in range(3))
        t1, _ = _evaluate_upper_limb_segment(seg, "L", 0.8, r1, 42.0)
        t2, _ = _evaluate_upper_limb_segment(seg, "L", 0.8, r2, 42.0)
        assert t1 is not None and t2 is not None and t1.pole_hint_world_xyz is not None and t2.pole_hint_world_xyz is not None
        delta_wrist = tuple(t2.world_xyz[i] - t1.world_xyz[i] for i in range(3))
        delta_pole = tuple(t2.pole_hint_world_xyz[i] - t1.pole_hint_world_xyz[i] for i in range(3))
        err_w = _vec_max_err(delta_wrist, delta_root)
        err_p = _vec_max_err(delta_pole, delta_root)
        assert err_w <= TOL and err_p <= TOL, (delta_root, delta_wrist, delta_pole)
        return {
            "root_1": list(r1),
            "root_2": list(r2),
            "expected_delta": list(delta_root),
            "actual_wrist_delta": list(delta_wrist),
            "actual_pole_delta": list(delta_pole),
            "wrist_abs_err": err_w,
            "pole_abs_err": err_p,
        }

    # T08 — ElbowPole contract (WORLD, ROOT_LOCAL, yaw/root sensitivity, interpolation, None)
    def test_t08() -> Dict[str, Any]:
        ps = (-0.2, -0.4, 1.0)
        pe = (-0.6, -0.8, 1.4)
        seg_world = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.0, 0.0, 1.0),
            wrist_end_xyz=(0.0, 0.0, 1.0),
            pole_start_xyz=ps,
            pole_end_xyz=pe,
            position_space="WORLD",
        )
        tw0, _ = _evaluate_upper_limb_segment(seg_world, "L", 1.0, (5.0, 6.0, 7.0), 90.0)
        exp_mid = (-0.4, -0.6, 1.2)
        assert tw0 is not None and tw0.pole_hint_world_xyz is not None
        err_w = _vec_max_err(tw0.pole_hint_world_xyz, exp_mid)
        assert err_w <= TOL

        seg_local = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.0, 0.5, 1.0),
            wrist_end_xyz=(0.0, 0.5, 1.0),
            pole_start_xyz=(1.0, 2.0, 3.0),
            pole_end_xyz=(1.0, 2.0, 3.0),
            position_space="ROOT_LOCAL",
        )
        tl_90, _ = _evaluate_upper_limb_segment(seg_local, "L", 1.0, (10.0, 20.0, 30.0), 90.0)
        tl_shifted, _ = _evaluate_upper_limb_segment(seg_local, "L", 1.0, (15.0, 25.0, 35.0), 90.0)
        assert tl_90 is not None and tl_shifted is not None
        exp_l90 = (8.0, 21.0, 33.0)
        exp_lshifted = (13.0, 26.0, 38.0)
        err_l1 = _vec_max_err(tl_90.pole_hint_world_xyz, exp_l90)
        err_l2 = _vec_max_err(tl_shifted.pole_hint_world_xyz, exp_lshifted)
        assert err_l1 <= TOL and err_l2 <= TOL
        # Prove pole includes Root translation (is a position, not a direction vector)
        assert tl_90.pole_hint_world_xyz != tl_shifted.pole_hint_world_xyz

        seg_none = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.0, 0.5, 1.0),
            wrist_end_xyz=(0.0, 0.5, 1.0),
            pole_start_xyz=None,
            pole_end_xyz=None,
        )
        tn, _ = _evaluate_upper_limb_segment(seg_none, "R", 1.0, (10.0, 20.0, 30.0), 90.0)
        assert tn is not None and tn.pole_hint_world_xyz is None
        return {
            "world_mid": {"expected": list(exp_mid), "actual": list(tw0.pole_hint_world_xyz), "abs_err": err_w},
            "local_yaw90": {"expected": list(exp_l90), "actual": list(tl_90.pole_hint_world_xyz), "abs_err": err_l1},
            "local_root_shifted": {"expected": list(exp_lshifted), "actual": list(tl_shifted.pole_hint_world_xyz), "abs_err": err_l2},
            "pole_none": {"expected": None, "actual": tn.pole_hint_world_xyz},
        }

    # T09 — Hand rotation contract (3-axis, endpoints, None, world invariance, no wraparound)
    def test_t09() -> Dict[str, Any]:
        # No implicit modulo / shortest-path wraparound check
        seg_wrap = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.1, 0.2, 0.3),
            wrist_end_xyz=(0.4, 0.5, 0.6),
            rotation_start_deg=(170.0, -170.0, 350.0),
            rotation_end_deg=(-170.0, 170.0, 10.0),
            position_space="WORLD",
        )
        t_start, _ = _evaluate_upper_limb_segment(seg_wrap, "L", 0.0, (0.0, 0.0, 0.0), 0.0)
        t_mid, _ = _evaluate_upper_limb_segment(seg_wrap, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
        t_end, _ = _evaluate_upper_limb_segment(seg_wrap, "L", 2.0, (0.0, 0.0, 0.0), 0.0)
        assert t_start is not None and t_mid is not None and t_end is not None
        assert t_start.rotation_deg == (170.0, -170.0, 350.0)
        assert _vec_max_err(t_mid.rotation_deg, (0.0, 0.0, 180.0)) <= TOL
        assert t_end.rotation_deg == (-170.0, 170.0, 10.0)

        seg_local_rot = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.1, 0.2, 0.3),
            wrist_end_xyz=(0.4, 0.5, 0.6),
            rotation_start_deg=(10.0, 20.0, 30.0),
            rotation_end_deg=(370.0, -40.0, 90.0),
            position_space="ROOT_LOCAL",
        )
        r_yaw0, _ = _evaluate_upper_limb_segment(seg_local_rot, "R", 1.0, (5.0, 6.0, 7.0), 0.0)
        r_yaw90, _ = _evaluate_upper_limb_segment(seg_local_rot, "R", 1.0, (5.0, 6.0, 7.0), 90.0)
        r_yawm135, _ = _evaluate_upper_limb_segment(seg_local_rot, "R", 1.0, (-3.0, 9.0, 1.0), -135.0)
        exp_rot_mid = (190.0, -10.0, 60.0)
        assert r_yaw0 is not None and r_yaw90 is not None and r_yawm135 is not None
        assert _vec_max_err(r_yaw0.rotation_deg, exp_rot_mid) <= TOL
        assert r_yaw0.rotation_deg == r_yaw90.rotation_deg == r_yawm135.rotation_deg

        seg_none = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.1, 0.2, 0.3),
            wrist_end_xyz=(0.4, 0.5, 0.6),
            rotation_start_deg=None,
            rotation_end_deg=None,
        )
        t_none, _ = _evaluate_upper_limb_segment(seg_none, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
        assert t_none is not None and t_none.rotation_deg is None
        return {
            "no_wraparound_mid": {"expected": [0.0, 0.0, 180.0], "actual": list(t_mid.rotation_deg)},
            "root_local_world_rot_mid": {"expected": list(exp_rot_mid), "actual": list(r_yaw90.rotation_deg)},
            "rotation_none": {"expected": None, "actual": t_none.rotation_deg},
        }

    # T10 — Reach clamp propagation and non-bool rejection
    def test_t10() -> Dict[str, Any]:
        seg_t = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), clamp_reach=True)
        seg_f = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), clamp_reach=False)
        res_t, _ = _evaluate_upper_limb_segment(seg_t, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
        res_f, _ = _evaluate_upper_limb_segment(seg_f, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
        assert res_t is not None and res_t.clamp_reach is True and type(res_t.clamp_reach) is bool
        assert res_f is not None and res_f.clamp_reach is False and type(res_f.clamp_reach) is bool
        neg = []
        for bad in (1, 0, "true", None):
            seg_bad = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), clamp_reach=bad)  # type: ignore[arg-type]
            raised = None
            try:
                _evaluate_upper_limb_segment(seg_bad, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == "TypeError", (bad, raised)
            neg.append({"input_clamp_reach": repr(bad), "expected": "TypeError", "actual": raised})
        return {"true_out": res_t.clamp_reach, "false_out": res_f.clamp_reach, "negative": neg}

    # T11 — IK vs contact intent decoupling
    def test_t11() -> Dict[str, Any]:
        seg = UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=1.0,
            wrist_start_xyz=(0.2, 0.5, 1.2),
            wrist_end_xyz=(0.3, 0.6, 1.3),
        )
        target, fk = _evaluate_upper_limb_segment(seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
        assert target is not None and fk == {}
        assert isinstance(target, PlannedHandTarget)
        assert target.enabled is True
        assert target.weight == 1.0
        assert target.contact_intent is False
        assert target.is_locked is False
        assert target.contact_type == ContactType.FREE
        assert target.surface_id is None
        return {
            "actual": {
                "enabled": target.enabled,
                "weight": target.weight,
                "contact_intent": target.contact_intent,
                "is_locked": target.is_locked,
                "contact_type": target.contact_type.value,
                "surface_id": target.surface_id,
                "fk": fk,
            }
        }

    # T12 — Left/right mixed FK/IK combinations (planning-target expression isolation only)
    def test_t12() -> Dict[str, Any]:
        fk_seg = UpperLimbSegment("FK", 0.0, 2.0, fk_start_deg=((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 0.0, 0.0)), fk_end_deg=((20.0, 0.0, 0.0), (30.0, 0.0, 0.0), (10.0, 0.0, 0.0)))
        ik_seg = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.2, 0.4, 1.2), wrist_end_xyz=(0.3, 0.5, 1.3))
        combos = [
            ("L_FK_R_IK", ("L", fk_seg), ("R", ik_seg)),
            ("L_IK_R_FK", ("L", ik_seg), ("R", fk_seg)),
            ("BOTH_FK", ("L", fk_seg), ("R", fk_seg)),
            ("BOTH_IK", ("L", ik_seg), ("R", ik_seg)),
        ]
        subcases = []
        for label, (s1, seg1), (s2, seg2) in combos:
            h1, fk1 = _evaluate_upper_limb_segment(seg1, s1, 1.0, (0.0, 0.0, 0.0), 0.0)
            h2, fk2 = _evaluate_upper_limb_segment(seg2, s2, 1.0, (0.0, 0.0, 0.0), 0.0)
            assert set(fk1.keys()).isdisjoint(set(fk2.keys()))
            if seg1.mode == "FK":
                assert h1 is None and len(fk1) == 3 and all(k.endswith(f".{s1}") for k in fk1)
            else:
                assert h1 is not None and h1.enabled is True and fk1 == {}
            if seg2.mode == "FK":
                assert h2 is None and len(fk2) == 3 and all(k.endswith(f".{s2}") for k in fk2)
            else:
                assert h2 is not None and h2.enabled is True and fk2 == {}
            subcases.append({"combo": label, "left_mode": seg1.mode, "right_mode": seg2.mode, "disjoint_fk_keys": True})
        return {
            "scope_note": "Validates planning-target expression isolation only; does not claim Blender runtime bone arbitration.",
            "subcases": subcases,
        }

    # T13 — Left/right trajectory parameter independence
    def test_t13() -> Dict[str, Any]:
        right_seg = UpperLimbSegment(
            mode="IK",
            start_time_sec=1.0,
            duration_sec=2.0,
            wrist_start_xyz=(-0.2, 0.3, 1.1),
            wrist_end_xyz=(-0.4, 0.5, 1.3),
            rotation_start_deg=(5.0, 10.0, 15.0),
            rotation_end_deg=(25.0, 30.0, 35.0),
            pole_start_xyz=(-0.3, -0.2, 1.0),
            pole_end_xyz=(-0.5, -0.4, 1.2),
            position_space="ROOT_LOCAL",
        )
        base_left = UpperLimbSegment(
            mode="IK",
            start_time_sec=1.0,
            duration_sec=2.0,
            wrist_start_xyz=(0.2, 0.3, 1.1),
            wrist_end_xyz=(0.4, 0.5, 1.3),
            rotation_start_deg=(-5.0, -10.0, -15.0),
            rotation_end_deg=(-25.0, -30.0, -35.0),
            pole_start_xyz=(0.3, -0.2, 1.0),
            pole_end_xyz=(0.5, -0.4, 1.2),
            position_space="ROOT_LOCAL",
        )
        r_ref, _ = _evaluate_upper_limb_segment(right_seg, "R", 1.5, (1.0, 2.0, 0.0), 30.0)
        l_ref, _ = _evaluate_upper_limb_segment(base_left, "L", 1.5, (1.0, 2.0, 0.0), 30.0)
        mutations = [
            ("start_time_sec", UpperLimbSegment("IK", 0.5, 2.0, None, None, base_left.wrist_start_xyz, base_left.wrist_end_xyz, base_left.rotation_start_deg, base_left.rotation_end_deg, base_left.pole_start_xyz, base_left.pole_end_xyz, "ROOT_LOCAL")),
            ("duration_sec", UpperLimbSegment("IK", 1.0, 4.0, None, None, base_left.wrist_start_xyz, base_left.wrist_end_xyz, base_left.rotation_start_deg, base_left.rotation_end_deg, base_left.pole_start_xyz, base_left.pole_end_xyz, "ROOT_LOCAL")),
            ("wrist_start_xyz", UpperLimbSegment("IK", 1.0, 2.0, None, None, (0.8, 0.9, 1.4), base_left.wrist_end_xyz, base_left.rotation_start_deg, base_left.rotation_end_deg, base_left.pole_start_xyz, base_left.pole_end_xyz, "ROOT_LOCAL")),
            ("wrist_end_xyz", UpperLimbSegment("IK", 1.0, 2.0, None, None, base_left.wrist_start_xyz, (0.9, 1.1, 1.7), base_left.rotation_start_deg, base_left.rotation_end_deg, base_left.pole_start_xyz, base_left.pole_end_xyz, "ROOT_LOCAL")),
            ("rotation", UpperLimbSegment("IK", 1.0, 2.0, None, None, base_left.wrist_start_xyz, base_left.wrist_end_xyz, (12.0, 0.0, 0.0), (45.0, 10.0, 0.0), base_left.pole_start_xyz, base_left.pole_end_xyz, "ROOT_LOCAL")),
            ("pole", UpperLimbSegment("IK", 1.0, 2.0, None, None, base_left.wrist_start_xyz, base_left.wrist_end_xyz, base_left.rotation_start_deg, base_left.rotation_end_deg, (0.9, -0.9, 1.5), (1.1, -1.1, 1.7), "ROOT_LOCAL")),
        ]
        subcases = []
        for field_changed, l_mod in mutations:
            l_out, _ = _evaluate_upper_limb_segment(l_mod, "L", 1.5, (1.0, 2.0, 0.0), 30.0)
            r_out, _ = _evaluate_upper_limb_segment(right_seg, "R", 1.5, (1.0, 2.0, 0.0), 30.0)
            assert l_out != l_ref, field_changed
            assert r_out == r_ref, field_changed
            subcases.append({"varied_left_field": field_changed, "left_changed": True, "right_unchanged": True})
        return {"subcases": subcases}

    # T14 — Enum and type rejection
    def test_t14() -> Dict[str, Any]:
        valid_seg = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0))
        subcases = []
        bad_seg_calls: List[Tuple[str, Any, str, type]] = [
            ("segment_none", None, "TypeError", TypeError),
            ("segment_dict", {"mode": "IK"}, "TypeError", TypeError),
            ("segment_str", "IK", "TypeError", TypeError),
        ]
        for label, bad_seg, exp_name, exp_cls in bad_seg_calls:
            raised = None
            try:
                _evaluate_upper_limb_segment(bad_seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)  # type: ignore[arg-type]
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_name and exp_cls.__name__ == exp_name
            subcases.append({"case": label, "expected": exp_name, "actual": raised})

        bad_sides: List[Tuple[str, Any, type]] = [
            ("side_M", "M", ValueError),
            ("side_lower", "l", ValueError),
            ("side_empty", "", ValueError),
            ("side_none", None, TypeError),
            ("side_int", 1, TypeError),
        ]
        for label, bad_side, exp_cls in bad_sides:
            raised = None
            try:
                _evaluate_upper_limb_segment(valid_seg, bad_side, 0.5, (0.0, 0.0, 0.0), 0.0)  # type: ignore[arg-type]
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, (label, raised)
            subcases.append({"case": label, "expected": exp_cls.__name__, "actual": raised})

        bad_modes: List[Tuple[str, Any, type]] = [
            ("mode_hybrid", "HYBRID", ValueError),
            ("mode_lower", "ik", ValueError),
            ("mode_none", None, TypeError),
            ("mode_int", 123, TypeError),
        ]
        for label, bad_mode, exp_cls in bad_modes:
            seg = UpperLimbSegment(bad_mode, 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0))  # type: ignore[arg-type]
            raised = None
            try:
                _evaluate_upper_limb_segment(seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, (label, raised)
            subcases.append({"case": label, "expected": exp_cls.__name__, "actual": raised})

        bad_spaces: List[Tuple[str, Any, type]] = [
            ("space_local", "LOCAL", ValueError),
            ("space_world_lower", "world", ValueError),
            ("space_none", None, TypeError),
            ("space_bool", True, TypeError),
        ]
        for label, bad_space, exp_cls in bad_spaces:
            seg = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), position_space=bad_space)  # type: ignore[arg-type]
            raised = None
            try:
                _evaluate_upper_limb_segment(seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, (label, raised)
            subcases.append({"case": label, "expected": exp_cls.__name__, "actual": raised})
        return {"subcases_count": len(subcases), "subcases": subcases}

    # T15 — Vector & root_yaw rejection
    def test_t15() -> Dict[str, Any]:
        subcases = []
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
            calls: List[Tuple[str, UpperLimbSegment, Any]] = [
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
        return {"subcases_count": len(subcases), "subcases": subcases[:20], "truncated_after": 20}

    # T16 — Mode/field conflicts and missing endpoints
    def test_t16() -> Dict[str, Any]:
        ok3 = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        v3 = (0.0, 0.0, 1.0)
        conflicts: List[Tuple[str, UpperLimbSegment, type]] = [
            ("fk_missing_start", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=None, fk_end_deg=ok3), ValueError),
            ("fk_missing_end", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=None), ValueError),
            ("fk_wrong_outer_len", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=(v3, v3), fk_end_deg=ok3), ValueError),
            ("fk_wrong_outer_type", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=[v3, v3, v3], fk_end_deg=ok3), TypeError),  # type: ignore[arg-type]
            ("fk_with_wrist_start", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, wrist_start_xyz=v3), ValueError),
            ("fk_with_wrist_end", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, wrist_end_xyz=v3), ValueError),
            ("fk_with_rot_start", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, rotation_start_deg=v3), ValueError),
            ("fk_with_rot_end", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, rotation_end_deg=v3), ValueError),
            ("fk_with_pole_start", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, pole_start_xyz=v3), ValueError),
            ("fk_with_pole_end", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, pole_end_xyz=v3), ValueError),
            ("fk_root_local", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, position_space="ROOT_LOCAL"), ValueError),
            ("ik_missing_wrist_start", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=None, wrist_end_xyz=v3), ValueError),
            ("ik_missing_wrist_end", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=None), ValueError),
            ("ik_with_fk_start", UpperLimbSegment("IK", 0.0, 1.0, fk_start_deg=ok3, wrist_start_xyz=v3, wrist_end_xyz=v3), ValueError),
            ("ik_with_fk_end", UpperLimbSegment("IK", 0.0, 1.0, fk_end_deg=ok3, wrist_start_xyz=v3, wrist_end_xyz=v3), ValueError),
            ("ik_rot_only_start", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, rotation_start_deg=v3, rotation_end_deg=None), ValueError),
            ("ik_rot_only_end", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, rotation_start_deg=None, rotation_end_deg=v3), ValueError),
            ("ik_pole_only_start", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, pole_start_xyz=v3, pole_end_xyz=None), ValueError),
            ("ik_pole_only_end", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, pole_start_xyz=None, pole_end_xyz=v3), ValueError),
        ]
        subcases = []
        for label, seg, exp_cls in conflicts:
            raised = None
            try:
                _evaluate_upper_limb_segment(seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, (label, raised)
            subcases.append({"case": label, "expected": exp_cls.__name__, "actual": raised})
        return {"subcases_count": len(subcases), "subcases": subcases}

    # T17 — Temporal error propagation and derived calculation overflow
    def test_t17() -> Dict[str, Any]:
        subcases = []
        v3 = (0.0, 0.0, 1.0)
        temporal_bad: List[Tuple[str, UpperLimbSegment, Any, type]] = [
            ("neg_time_sec", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), -0.1, ValueError),
            ("zero_duration", UpperLimbSegment("IK", 0.0, 0.0, wrist_start_xyz=v3, wrist_end_xyz=v3), 0.0, ValueError),
            ("nan_time_sec", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), float("nan"), ValueError),
            ("bool_time_sec", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), True, TypeError),
            ("end_time_overflow", UpperLimbSegment("IK", 1e308, 1e308, wrist_start_xyz=v3, wrist_end_xyz=v3), 1.0, ValueError),
            ("precision_loss", UpperLimbSegment("IK", 1e16, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), 1e16, ValueError),
        ]
        for label, seg, t_val, exp_cls in temporal_bad:
            raised = None
            try:
                _evaluate_upper_limb_segment(seg, "L", t_val, (0.0, 0.0, 0.0), 0.0)
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == exp_cls.__name__, (label, raised)
            subcases.append({"case": label, "expected": exp_cls.__name__, "actual": raised})

        # Derived transform & translation overflows
        overflow_cases: List[Tuple[str, UpperLimbSegment, Tuple[float, float, float], float]] = [
            (
                "local_yaw45_rotation_overflow",
                UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(1.5e308, 1.5e308, 0.0), wrist_end_xyz=(1.5e308, 1.5e308, 0.0), position_space="ROOT_LOCAL"),
                (0.0, 0.0, 0.0),
                45.0,
            ),
            (
                "wrist_root_translation_overflow",
                UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(1e308, 0.0, 0.0), wrist_end_xyz=(1e308, 0.0, 0.0), position_space="ROOT_LOCAL"),
                (1e308, 0.0, 0.0),
                0.0,
            ),
            (
                "pole_root_translation_overflow",
                UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), pole_start_xyz=(1e308, 0.0, 0.0), pole_end_xyz=(1e308, 0.0, 0.0), position_space="ROOT_LOCAL"),
                (1e308, 0.0, 0.0),
                0.0,
            ),
        ]
        for label, seg, r_pos, r_yaw in overflow_cases:
            raised = None
            try:
                _evaluate_upper_limb_segment(seg, "L", 0.5, r_pos, r_yaw)
            except Exception as exc:
                raised = type(exc).__name__
            assert raised == "ValueError", (label, raised)
            subcases.append({"case": label, "expected": "ValueError", "actual": raised})
        return {"subcases": subcases}

    # T18 — Frozen dataclass, input immutability, return isolation & determinism
    def test_t18() -> Dict[str, Any]:
        s_rot = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0))
        e_rot = ((11.0, 12.0, 13.0), (14.0, 15.0, 16.0), (17.0, 18.0, 19.0))
        fk_seg = UpperLimbSegment("FK", 1.0, 2.0, fk_start_deg=s_rot, fk_end_deg=e_rot)
        ik_seg = UpperLimbSegment("IK", 1.0, 2.0, wrist_start_xyz=(0.2, 0.4, 1.1), wrist_end_xyz=(0.4, 0.6, 1.3), rotation_start_deg=(1.0, 2.0, 3.0), rotation_end_deg=(4.0, 5.0, 6.0), pole_start_xyz=(-0.1, -0.2, 1.0), pole_end_xyz=(-0.2, -0.3, 1.1), position_space="ROOT_LOCAL")

        # Frozen check
        frozen_exc = None
        try:
            fk_seg.mode = "IK"  # type: ignore[misc]
        except Exception as exc:
            frozen_exc = type(exc).__name__
        assert frozen_exc in ("FrozenInstanceError", "AttributeError")

        root_in = (2.0, -3.0, 0.5)
        t_fk_1, d_fk_1 = _evaluate_upper_limb_segment(fk_seg, "L", 1.5, root_in, 25.0)
        assert t_fk_1 is None
        d_fk_snap = dict(d_fk_1)
        d_fk_1["hand.L"] = (999.0, 999.0, 999.0)
        d_fk_1.clear()
        t_fk_2, d_fk_2 = _evaluate_upper_limb_segment(fk_seg, "L", 1.5, root_in, 25.0)
        assert t_fk_2 is None and d_fk_2 == d_fk_snap

        t_ik_1, fk_ik_1 = _evaluate_upper_limb_segment(ik_seg, "R", 1.5, root_in, 25.0)
        assert t_ik_1 is not None and fk_ik_1 == {}
        snap_xyz = t_ik_1.world_xyz
        snap_rot = t_ik_1.rotation_deg
        snap_pole = t_ik_1.pole_hint_world_xyz
        t_ik_1.world_xyz = (999.0, 999.0, 999.0)
        t_ik_1.enabled = False
        t_ik_2, fk_ik_2 = _evaluate_upper_limb_segment(ik_seg, "R", 1.5, root_in, 25.0)
        assert t_ik_2 is not None and fk_ik_2 == {}
        assert t_ik_2.world_xyz == snap_xyz and t_ik_2.rotation_deg == snap_rot and t_ik_2.pole_hint_world_xyz == snap_pole and t_ik_2.enabled is True
        assert root_in == (2.0, -3.0, 0.5) and s_rot[0] == (1.0, 2.0, 3.0)
        return {
            "frozen_exception": frozen_exc,
            "fk_isolated_after_caller_mutation": True,
            "ik_isolated_after_caller_mutation": True,
            "inputs_unmodified": True,
        }

    tests: List[Tuple[str, str, Callable[[], Dict[str, Any]]]] = [
        ("T01", "FK 时间边界", test_t01),
        ("T02", "FK 独立三轴插值", test_t02),
        ("T03", "左右侧隔离", test_t03),
        ("T04", "IK 世界空间插值", test_t04),
        ("T05", "IK Root 局部空间转换", test_t05),
        ("T06", "偏航角数学合同", test_t06),
        ("T07", "Root 平移反事实", test_t07),
        ("T08", "ElbowPole 合同", test_t08),
        ("T09", "手部姿态合同", test_t09),
        ("T10", "Reach Clamp", test_t10),
        ("T11", "IK 与接触分离", test_t11),
        ("T12", "左右 FK/IK 混合目标", test_t12),
        ("T13", "左右轨迹参数独立", test_t13),
        ("T14", "枚举及类型拒绝", test_t14),
        ("T15", "向量输入与 Root yaw 拒绝", test_t15),
        ("T16", "模式字段冲突", test_t16),
        ("T17", "时间及派生计算边界", test_t17),
        ("T18", "无状态性与输入不变性", test_t18),
    ]
    for tid, title, fn in tests:
        run_test(tid, title, fn)

    passed = sum(1 for r in records if r["status"] == "PASS")
    failed = sum(1 for r in records if r["status"] != "PASS")
    exit_code = 0 if failed == 0 and passed == 18 else 1

    payload = {
        "task": "TASK 10-d-3 — 独立上肢轨迹目标专项验证",
        "command": " ".join([sys.executable, "-B", "docs/evidence/10-d/10-d-3/verify_upper_limb_segment.py"]),
        "exit_code": exit_code,
        "source_baseline": baseline,
        "summary": {
            "executed": len(records),
            "passed": passed,
            "failed": failed,
        },
        "tests": records,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SUMMARY: passed={passed} failed={failed} executed={len(records)} exit_code={exit_code}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
