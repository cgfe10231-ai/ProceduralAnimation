"""TASK 10-D Final Acceptance — Current Production Verification for Migrated Modules.

Directly imports and verifies the current production implementations at HEAD
whose symbols were migrated or modified during Task 10-D:
  1. 10-d-2 contract (12/12 tests): src.motion.upper_limb_trajectory._evaluate_upper_limb_progress
  2. 10-d-3 contract (18/18 tests, all 68 T15 subcases untruncated):
     UpperLimbSegment, _validate_upper_limb_vector, _evaluate_upper_limb_segment
  3. TerrainWalkAction compatibility re-exports from src.motion.terrain_walk
  4. 10-d-4 repeat-execution upper-limb curve cleanup & Phase 6 Influence FCurve persistence
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = Path(__file__).resolve().parent / "migrated_checks"


def _run_10d2_migrated() -> Dict[str, Any]:
    from src.motion import terrain_walk as tw
    from src.motion.upper_limb_trajectory import _evaluate_upper_limb_progress as fn

    assert tw._evaluate_upper_limb_progress is fn, "terrain_walk re-export mismatch"
    records: List[Dict[str, Any]] = []

    def run_test(test_id: str, title: str, body: Callable[[], Dict[str, Any]]) -> None:
        detail = body()
        records.append({"id": test_id, "title": title, "status": "PASS", **detail})

    def test_t01() -> Dict[str, Any]:
        for t, s, d in ((0.0, 2.0, 3.0), (0.5, 2.0, 3.0), (1.999999, 2.0, 3.0), (2.0, 2.0, 3.0), (0.0, 0.0, 1.5), (-0.0, 0.0, 1.5)):
            out = fn(t, s, d)
            assert out == (0.0, 0.0) and isinstance(out, tuple)
            assert not math.copysign(1.0, out[0]) < 0.0 and not math.copysign(1.0, out[1]) < 0.0
        return {"checked": 6}

    def test_t02() -> Dict[str, Any]:
        for t, s, d in ((5.0, 2.0, 3.0), (1.5, 0.0, 1.5), (5.000001, 2.0, 3.0), (100.0, 2.0, 3.0)):
            out = fn(t, s, d)
            assert out == (1.0, 1.0) and isinstance(out, tuple)
        return {"checked": 4}

    def test_t03() -> Dict[str, Any]:
        max_abs_err = 0.0
        for target_u, exp_h in ((0.25, 0.103515625), (0.5, 0.5), (0.75, 0.896484375)):
            for s, d in ((0.0, 1.0), (1.0, 4.0)):
                u, h = fn(s + target_u * d, s, d)
                max_abs_err = max(max_abs_err, abs(u - target_u), abs(h - exp_h))
                assert max_abs_err <= 1e-12
        return {"max_abs_err": max_abs_err}

    def test_t04() -> Dict[str, Any]:
        sample_count = 10001
        for s, d in ((0.0, 1.0), (1.25, 2.5)):
            pu, ph = -1.0, -1.0
            for i in range(sample_count):
                u, h = fn(s + (i / (sample_count - 1)) * d, s, d)
                assert math.isfinite(u) and math.isfinite(h) and 0.0 <= u <= 1.0 and 0.0 <= h <= 1.0
                assert u >= pu and h >= ph
                pu, ph = u, h
        return {"sample_count_per_interval": sample_count}

    def test_t05() -> Dict[str, Any]:
        max_poly_diff = 0.0
        for i in range(101):
            uf = Fraction(i, 100)
            h_ex = float(10 * uf**3 - 15 * uf**4 + 6 * uf**5)
            _, h_fn = fn(i / 100.0, 0.0, 1.0)
            max_poly_diff = max(max_poly_diff, abs(h_fn - h_ex))
            assert max_poly_diff <= 1e-12
        conv = []
        for delta in (1e-3, 1e-4, 1e-5):
            _, h0 = fn(0.0, 0.0, 1.0)
            _, hd1 = fn(delta, 0.0, 1.0)
            _, hd2 = fn(2.0 * delta, 0.0, 1.0)
            _, h1 = fn(1.0, 0.0, 1.0)
            _, hm1 = fn(1.0 - delta, 0.0, 1.0)
            _, hm2 = fn(1.0 - 2.0 * delta, 0.0, 1.0)
            conv.append((abs((hd1 - h0) / delta), abs((hd2 - 2 * hd1 + h0) / (delta**2)), abs((h1 - hm1) / delta), abs((h1 - 2 * hm1 + hm2) / (delta**2))))
        for idx in range(1, len(conv)):
            for k in range(4):
                assert conv[idx][k] < conv[idx - 1][k]
        assert conv[-1][0] < 1e-6 and conv[-1][2] < 1e-6 and conv[-1][1] < 1e-2 and conv[-1][3] < 1e-2
        return {"max_poly_diff": max_poly_diff}

    def test_t06() -> Dict[str, Any]:
        cnt = 0
        for p_idx in range(3):
            for bad_val in (True, False, None, "1.0", [1.0], 1.0 + 0j):
                args = [1.0, 1.0, 1.0]
                args[p_idx] = bad_val
                try:
                    fn(*args)
                    raise AssertionError("Expected TypeError")
                except TypeError:
                    cnt += 1
        return {"subcases": cnt}

    def test_t07() -> Dict[str, Any]:
        cnt = 0
        for p_idx in range(3):
            for bad_val in (float("nan"), float("inf"), float("-inf")):
                args = [1.0, 1.0, 1.0]
                args[p_idx] = bad_val
                try:
                    fn(*args)
                    raise AssertionError("Expected ValueError")
                except ValueError:
                    cnt += 1
        return {"subcases": cnt}

    def test_t08() -> Dict[str, Any]:
        cases = ((-1e-6, 0.0, 1.0), (-1, 0.0, 1.0), (0.0, -1e-6, 1.0), (1.0, -2.5, 1.0), (0.5, 0.0, 0), (0.5, 0.0, 0.0), (0.5, 0.0, -0.0), (0.5, 0.0, -1e-6), (0.5, 0.0, -2.0))
        for args in cases:
            try:
                fn(*args)
                raise AssertionError(f"Expected ValueError for {args}")
            except ValueError:
                pass
        return {"subcases": len(cases)}

    def test_t09() -> Dict[str, Any]:
        cases = ((10**400, 0.0, 1.0), (0.0, 10**400, 1.0), (0.0, 0.0, 10**400), (1.0, 1e308, 1e308), (1e16, 1e16, 1.0), (1.0, 1.0, 1e-16))
        for args in cases:
            try:
                fn(*args)
                raise AssertionError(f"Expected ValueError for {args}")
            except ValueError:
                pass
        return {"subcases": len(cases)}

    def test_t10() -> Dict[str, Any]:
        l = fn(2.5, 1.0, 2.0)
        r = fn(2.5, 2.0, 2.0)
        assert l == (0.75, 0.896484375) and r == (0.25, 0.103515625) and l != r
        return {"left": list(l), "right": list(r)}

    def test_t11() -> Dict[str, Any]:
        l = fn(2.0, 1.0, 2.0)
        r = fn(2.0, 1.0, 4.0)
        assert l == (0.5, 0.5) and r == (0.25, 0.103515625) and l != r
        return {"left": list(l), "right": list(r)}

    def test_t12() -> Dict[str, Any]:
        pa, pb = (2.37, 1.2, 2.6), (4.15, 3.0, 1.8)
        ba, bb = fn(*pa), fn(*pb)
        for _ in range(50):
            assert fn(*pa) == ba and fn(*pb) == bb
            assert fn(0.2, 1.2, 2.6) == (0.0, 0.0) and fn(9.9, 3.0, 1.8) == (1.0, 1.0)
            for bad in ((-1.0, 0.0, 1.0), (True, 0.0, 1.0)):
                try:
                    fn(*bad)
                except (ValueError, TypeError):
                    pass
        assert fn(*pa) == ba and fn(*pb) == bb
        return {"cycles": 50}

    for tid, title, body in (
        ("T01", "开始前及开始时边界", test_t01),
        ("T02", "结束时及结束后边界", test_t02),
        ("T03", "五次插值数学正确性", test_t03),
        ("T04", "进度单调性与值域", test_t04),
        ("T05", "端点解析导数与有限差分收敛", test_t05),
        ("T06", "非法类型拒绝", test_t06),
        ("T07", "非有限数值拒绝", test_t07),
        ("T08", "时间与持续时间范围拒绝", test_t08),
        ("T09", "数值溢出与精度退化拒绝", test_t09),
        ("T10", "左右独立开始时间", test_t10),
        ("T11", "左右独立持续时间", test_t11),
        ("T12", "重复与交替调用无状态性", test_t12),
    ):
        run_test(tid, title, body)

    return {"passed": len(records), "failed": 0, "total": 12, "tests": records}


def _run_10d3_migrated() -> Dict[str, Any]:
    from src.motion import terrain_walk as tw
    from src.motion.contact_model import ContactType
    from src.motion.framework import root_local_to_world_vector
    from src.motion.kinematic_bridge import PlannedHandTarget
    from src.motion.upper_limb_trajectory import (
        UpperLimbSegment,
        _evaluate_upper_limb_progress,
        _evaluate_upper_limb_segment,
        _validate_upper_limb_vector,
    )

    assert tw.UpperLimbSegment is UpperLimbSegment
    assert tw._evaluate_upper_limb_segment is _evaluate_upper_limb_segment
    assert tw._validate_upper_limb_vector is _validate_upper_limb_vector

    TOL = 1e-12
    records: List[Dict[str, Any]] = []

    def _vec_max_err(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
        return max(abs(x - y) for x, y in zip(a, b))

    def test_t01() -> Dict[str, Any]:
        s_rot = ((0.0, 0.0, 0.0), (10.0, -20.0, 30.0), (-5.0, 15.0, -25.0))
        e_rot = ((20.0, -40.0, 60.0), (50.0, 20.0, -10.0), (15.0, -5.0, 55.0))
        seg = UpperLimbSegment("FK", 2.0, 4.0, fk_start_deg=s_rot, fk_end_deg=e_rot)
        max_err = 0.0
        for t in (0.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5):
            _, h = _evaluate_upper_limb_progress(t, 2.0, 4.0)
            target, fk = _evaluate_upper_limb_segment(seg, "L", t, (0.0, 0.0, 0.0), 0.0)
            assert target is None
            for b, sv, ev in zip(("upper_arm", "forearm", "hand"), s_rot, e_rot):
                exp = tuple((1.0 - h) * sv[j] + h * ev[j] for j in range(3))
                max_err = max(max_err, _vec_max_err(exp, fk[f"{b}.L"]))
                assert max_err <= TOL
        return {"max_abs_err": max_err}

    def test_t02() -> Dict[str, Any]:
        s_rot = ((10.0, -20.0, 30.0), (-40.0, 50.0, -60.0), (7.0, -8.0, 9.0))
        e_rot = ((30.0, 20.0, -10.0), (40.0, -30.0, 20.0), (-13.0, 32.0, 49.0))
        seg = UpperLimbSegment("FK", 1.0, 4.0, fk_start_deg=s_rot, fk_end_deg=e_rot)
        _, h = _evaluate_upper_limb_progress(2.0, 1.0, 4.0)
        target, fk = _evaluate_upper_limb_segment(seg, "R", 2.0, (1.0, 2.0, 3.0), 45.0)
        assert target is None
        max_err = 0.0
        for b, sv, ev in zip(("upper_arm", "forearm", "hand"), s_rot, e_rot):
            for j in range(3):
                max_err = max(max_err, abs(fk[f"{b}.R"][j] - ((1.0 - h) * sv[j] + h * ev[j])))
                assert max_err <= TOL
        return {"max_abs_err": max_err}

    def test_t03() -> Dict[str, Any]:
        rot = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0))
        seg = UpperLimbSegment("FK", 0.0, 2.0, fk_start_deg=rot, fk_end_deg=rot)
        tl, fk_l = _evaluate_upper_limb_segment(seg, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
        tr, fk_r = _evaluate_upper_limb_segment(seg, "R", 1.0, (0.0, 0.0, 0.0), 0.0)
        assert tl is None and tr is None
        assert sorted(fk_l) == ["forearm.L", "hand.L", "upper_arm.L"]
        assert sorted(fk_r) == ["forearm.R", "hand.R", "upper_arm.R"]
        return {"ok": True}

    def test_t04() -> Dict[str, Any]:
        ws, we = (0.3, -0.4, 1.1), (0.7, 0.8, 1.9)
        seg = UpperLimbSegment("IK", 2.0, 4.0, wrist_start_xyz=ws, wrist_end_xyz=we, position_space="WORLD")
        max_err = 0.0
        for t in (2.0, 3.0, 4.0, 6.0):
            _, h = _evaluate_upper_limb_progress(t, 2.0, 4.0)
            exp = tuple((1.0 - h) * ws[i] + h * we[i] for i in range(3))
            t1, fk1 = _evaluate_upper_limb_segment(seg, "L", t, (0.0, 0.0, 0.0), 0.0)
            t2, fk2 = _evaluate_upper_limb_segment(seg, "L", t, (100.0, -50.0, 25.0), 137.0)
            assert fk1 == {} and fk2 == {} and t1 is not None and t2 is not None and t1.world_xyz == t2.world_xyz
            max_err = max(max_err, _vec_max_err(t1.world_xyz, exp))
            assert max_err <= TOL
        return {"max_abs_err": max_err}

    def test_t05() -> Dict[str, Any]:
        ls, le = (0.2, 0.5, 0.3), (-0.4, 0.8, 0.9)
        rp, ry = (5.0, -3.0, 1.2), 37.0
        seg = UpperLimbSegment("IK", 1.0, 2.0, wrist_start_xyz=ls, wrist_end_xyz=le, position_space="ROOT_LOCAL")
        max_err = 0.0
        for t in (1.0, 1.5, 2.0, 3.0):
            _, h = _evaluate_upper_limb_progress(t, 1.0, 2.0)
            li = tuple((1.0 - h) * ls[i] + h * le[i] for i in range(3))
            wv = root_local_to_world_vector(li, ry)
            exp = tuple(rp[i] + wv[i] for i in range(3))
            tgt, fk = _evaluate_upper_limb_segment(seg, "R", t, rp, ry)
            assert fk == {} and tgt is not None
            max_err = max(max_err, _vec_max_err(tgt.world_xyz, exp))
            assert max_err <= TOL
        return {"max_abs_err": max_err}

    def test_t06() -> Dict[str, Any]:
        lp, rp = (1.0, 2.0, 3.0), (10.0, 20.0, 30.0)
        seg = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=lp, wrist_end_xyz=lp, position_space="ROOT_LOCAL")
        for yaw, exp in ((0.0, (11.0, 22.0, 33.0)), (90.0, (8.0, 21.0, 33.0)), (-90.0, (12.0, 19.0, 33.0)), (180.0, (9.0, 18.0, 33.0))):
            tgt, _ = _evaluate_upper_limb_segment(seg, "L", 0.5, rp, yaw)
            assert tgt is not None and _vec_max_err(tgt.world_xyz, exp) <= TOL
        return {"checked": 4}

    def test_t07() -> Dict[str, Any]:
        seg = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.2, 0.4, 0.6), wrist_end_xyz=(0.6, 0.8, 1.0), pole_start_xyz=(-0.1, -0.3, 0.4), pole_end_xyz=(-0.3, -0.5, 0.8), position_space="ROOT_LOCAL")
        r1, r2 = (1.5, -2.0, 0.5), (11.5, 4.0, -3.5)
        dr = tuple(r2[i] - r1[i] for i in range(3))
        t1, _ = _evaluate_upper_limb_segment(seg, "L", 0.8, r1, 42.0)
        t2, _ = _evaluate_upper_limb_segment(seg, "L", 0.8, r2, 42.0)
        assert t1 is not None and t2 is not None and t1.pole_hint_world_xyz is not None and t2.pole_hint_world_xyz is not None
        assert _vec_max_err(tuple(t2.world_xyz[i] - t1.world_xyz[i] for i in range(3)), dr) <= TOL
        assert _vec_max_err(tuple(t2.pole_hint_world_xyz[i] - t1.pole_hint_world_xyz[i] for i in range(3)), dr) <= TOL
        return {"ok": True}

    def test_t08() -> Dict[str, Any]:
        sw = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), pole_start_xyz=(-0.2, -0.4, 1.0), pole_end_xyz=(-0.6, -0.8, 1.4), position_space="WORLD")
        tw, _ = _evaluate_upper_limb_segment(sw, "L", 1.0, (5.0, 6.0, 7.0), 90.0)
        assert tw is not None and tw.pole_hint_world_xyz is not None and _vec_max_err(tw.pole_hint_world_xyz, (-0.4, -0.6, 1.2)) <= TOL
        sl = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.0, 0.5, 1.0), wrist_end_xyz=(0.0, 0.5, 1.0), pole_start_xyz=(1.0, 2.0, 3.0), pole_end_xyz=(1.0, 2.0, 3.0), position_space="ROOT_LOCAL")
        tl1, _ = _evaluate_upper_limb_segment(sl, "L", 1.0, (10.0, 20.0, 30.0), 90.0)
        tl2, _ = _evaluate_upper_limb_segment(sl, "L", 1.0, (15.0, 25.0, 35.0), 90.0)
        assert tl1 is not None and tl2 is not None and _vec_max_err(tl1.pole_hint_world_xyz, (8.0, 21.0, 33.0)) <= TOL and _vec_max_err(tl2.pole_hint_world_xyz, (13.0, 26.0, 38.0)) <= TOL
        sn = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.0, 0.5, 1.0), wrist_end_xyz=(0.0, 0.5, 1.0), pole_start_xyz=None, pole_end_xyz=None)
        tn, _ = _evaluate_upper_limb_segment(sn, "R", 1.0, (10.0, 20.0, 30.0), 90.0)
        assert tn is not None and tn.pole_hint_world_xyz is None
        return {"ok": True}

    def test_t09() -> Dict[str, Any]:
        sw = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.1, 0.2, 0.3), wrist_end_xyz=(0.4, 0.5, 0.6), rotation_start_deg=(170.0, -170.0, 350.0), rotation_end_deg=(-170.0, 170.0, 10.0), position_space="WORLD")
        t0, _ = _evaluate_upper_limb_segment(sw, "L", 0.0, (0.0, 0.0, 0.0), 0.0)
        tm, _ = _evaluate_upper_limb_segment(sw, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
        t1, _ = _evaluate_upper_limb_segment(sw, "L", 2.0, (0.0, 0.0, 0.0), 0.0)
        assert t0.rotation_deg == (170.0, -170.0, 350.0) and _vec_max_err(tm.rotation_deg, (0.0, 0.0, 180.0)) <= TOL and t1.rotation_deg == (-170.0, 170.0, 10.0)
        sl = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.1, 0.2, 0.3), wrist_end_xyz=(0.4, 0.5, 0.6), rotation_start_deg=(10.0, 20.0, 30.0), rotation_end_deg=(370.0, -40.0, 90.0), position_space="ROOT_LOCAL")
        r0, _ = _evaluate_upper_limb_segment(sl, "R", 1.0, (5.0, 6.0, 7.0), 0.0)
        r90, _ = _evaluate_upper_limb_segment(sl, "R", 1.0, (5.0, 6.0, 7.0), 90.0)
        rm, _ = _evaluate_upper_limb_segment(sl, "R", 1.0, (-3.0, 9.0, 1.0), -135.0)
        assert _vec_max_err(r0.rotation_deg, (190.0, -10.0, 60.0)) <= TOL and r0.rotation_deg == r90.rotation_deg == rm.rotation_deg
        sn = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.1, 0.2, 0.3), wrist_end_xyz=(0.4, 0.5, 0.6))
        rn, _ = _evaluate_upper_limb_segment(sn, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
        assert rn.rotation_deg is None
        return {"ok": True}

    def test_t10() -> Dict[str, Any]:
        rt, _ = _evaluate_upper_limb_segment(UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), clamp_reach=True), "L", 0.5, (0.0, 0.0, 0.0), 0.0)
        rf, _ = _evaluate_upper_limb_segment(UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), clamp_reach=False), "L", 0.5, (0.0, 0.0, 0.0), 0.0)
        assert rt.clamp_reach is True and rf.clamp_reach is False
        for bad in (1, 0, "true", None):
            try:
                _evaluate_upper_limb_segment(UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), clamp_reach=bad), "L", 0.5, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(bad)
            except TypeError:
                pass
        return {"ok": True}

    def test_t11() -> Dict[str, Any]:
        tgt, fk = _evaluate_upper_limb_segment(UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.2, 0.5, 1.2), wrist_end_xyz=(0.3, 0.6, 1.3)), "L", 0.5, (0.0, 0.0, 0.0), 0.0)
        assert fk == {} and isinstance(tgt, PlannedHandTarget)
        assert tgt.enabled is True and tgt.weight == 1.0 and tgt.contact_intent is False and tgt.is_locked is False and tgt.contact_type == ContactType.FREE and tgt.surface_id is None
        return {"ok": True}

    def test_t12() -> Dict[str, Any]:
        fk_s = UpperLimbSegment("FK", 0.0, 2.0, fk_start_deg=((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 0.0, 0.0)), fk_end_deg=((20.0, 0.0, 0.0), (30.0, 0.0, 0.0), (10.0, 0.0, 0.0)))
        ik_s = UpperLimbSegment("IK", 0.0, 2.0, wrist_start_xyz=(0.2, 0.4, 1.2), wrist_end_xyz=(0.3, 0.5, 1.3))
        for s1, s2 in ((fk_s, ik_s), (ik_s, fk_s), (fk_s, fk_s), (ik_s, ik_s)):
            h1, f1 = _evaluate_upper_limb_segment(s1, "L", 1.0, (0.0, 0.0, 0.0), 0.0)
            h2, f2 = _evaluate_upper_limb_segment(s2, "R", 1.0, (0.0, 0.0, 0.0), 0.0)
            assert set(f1).isdisjoint(set(f2)) and (h1 is None) == (s1.mode == "FK") and (h2 is None) == (s2.mode == "FK")
        return {"combos": 4}

    def test_t13() -> Dict[str, Any]:
        rs = UpperLimbSegment("IK", 1.0, 2.0, wrist_start_xyz=(-0.2, 0.3, 1.1), wrist_end_xyz=(-0.4, 0.5, 1.3), rotation_start_deg=(5.0, 10.0, 15.0), rotation_end_deg=(25.0, 30.0, 35.0), pole_start_xyz=(-0.3, -0.2, 1.0), pole_end_xyz=(-0.5, -0.4, 1.2), position_space="ROOT_LOCAL")
        bl = UpperLimbSegment("IK", 1.0, 2.0, wrist_start_xyz=(0.2, 0.3, 1.1), wrist_end_xyz=(0.4, 0.5, 1.3), rotation_start_deg=(-5.0, -10.0, -15.0), rotation_end_deg=(-25.0, -30.0, -35.0), pole_start_xyz=(0.3, -0.2, 1.0), pole_end_xyz=(0.5, -0.4, 1.2), position_space="ROOT_LOCAL")
        rr, _ = _evaluate_upper_limb_segment(rs, "R", 1.5, (1.0, 2.0, 0.0), 30.0)
        lr, _ = _evaluate_upper_limb_segment(bl, "L", 1.5, (1.0, 2.0, 0.0), 30.0)
        for lm in (
            UpperLimbSegment("IK", 0.5, 2.0, None, None, bl.wrist_start_xyz, bl.wrist_end_xyz, bl.rotation_start_deg, bl.rotation_end_deg, bl.pole_start_xyz, bl.pole_end_xyz, "ROOT_LOCAL"),
            UpperLimbSegment("IK", 1.0, 4.0, None, None, bl.wrist_start_xyz, bl.wrist_end_xyz, bl.rotation_start_deg, bl.rotation_end_deg, bl.pole_start_xyz, bl.pole_end_xyz, "ROOT_LOCAL"),
            UpperLimbSegment("IK", 1.0, 2.0, None, None, (0.8, 0.9, 1.4), bl.wrist_end_xyz, bl.rotation_start_deg, bl.rotation_end_deg, bl.pole_start_xyz, bl.pole_end_xyz, "ROOT_LOCAL"),
            UpperLimbSegment("IK", 1.0, 2.0, None, None, bl.wrist_start_xyz, (0.9, 1.1, 1.7), bl.rotation_start_deg, bl.rotation_end_deg, bl.pole_start_xyz, bl.pole_end_xyz, "ROOT_LOCAL"),
            UpperLimbSegment("IK", 1.0, 2.0, None, None, bl.wrist_start_xyz, bl.wrist_end_xyz, (12.0, 0.0, 0.0), (45.0, 10.0, 0.0), bl.pole_start_xyz, bl.pole_end_xyz, "ROOT_LOCAL"),
            UpperLimbSegment("IK", 1.0, 2.0, None, None, bl.wrist_start_xyz, bl.wrist_end_xyz, bl.rotation_start_deg, bl.rotation_end_deg, (0.9, -0.9, 1.5), (1.1, -1.1, 1.7), "ROOT_LOCAL"),
        ):
            lo, _ = _evaluate_upper_limb_segment(lm, "L", 1.5, (1.0, 2.0, 0.0), 30.0)
            ro, _ = _evaluate_upper_limb_segment(rs, "R", 1.5, (1.0, 2.0, 0.0), 30.0)
            assert lo != lr and ro == rr
        return {"mutations": 6}

    def test_t14() -> Dict[str, Any]:
        v = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0))
        cnt = 0
        for bad_seg in (None, {"mode": "IK"}, "IK"):
            try:
                _evaluate_upper_limb_segment(bad_seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(bad_seg)
            except TypeError:
                cnt += 1
        for bs, ec in (("M", ValueError), ("l", ValueError), ("", ValueError), (None, TypeError), (1, TypeError)):
            try:
                _evaluate_upper_limb_segment(v, bs, 0.5, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(bs)
            except ec:
                cnt += 1
        for bm, ec in (("HYBRID", ValueError), ("ik", ValueError), (None, TypeError), (123, TypeError)):
            try:
                _evaluate_upper_limb_segment(UpperLimbSegment(bm, 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0)), "L", 0.5, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(bm)
            except ec:
                cnt += 1
        for bsp, ec in (("LOCAL", ValueError), ("world", ValueError), (None, TypeError), (True, TypeError)):
            try:
                _evaluate_upper_limb_segment(UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(0.0, 0.0, 1.0), wrist_end_xyz=(0.0, 0.0, 1.0), position_space=bsp), "L", 0.5, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(bsp)
            except ec:
                cnt += 1
        return {"subcases": cnt}

    def test_t15() -> Dict[str, Any]:
        subcases = 0
        bad_vecs = (
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
        )
        for _, bad_v, exp_cls in bad_vecs:
            try:
                _validate_upper_limb_vector(bad_v, "test_vec")
                raise AssertionError(bad_v)
            except exp_cls:
                subcases += 1
        ok_rot = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        ok_v = (0.0, 0.0, 1.0)
        for _, bad_v, exp_cls in bad_vecs:
            calls = (
                ("wrist_start_xyz", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=bad_v, wrist_end_xyz=ok_v), ok_v),
                ("rotation_start_deg", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v, rotation_start_deg=bad_v, rotation_end_deg=ok_v), ok_v),
                ("pole_end_xyz", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v, pole_start_xyz=ok_v, pole_end_xyz=bad_v), ok_v),
                ("fk_start_deg_0", UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=(bad_v, ok_v, ok_v), fk_end_deg=ok_rot), ok_v),
                ("root_position", UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v), bad_v),
            )
            for fname, seg, rp in calls:
                ec = ValueError if (bad_v is None and fname not in ("root_position", "fk_start_deg_0")) else exp_cls
                try:
                    _evaluate_upper_limb_segment(seg, "L", 0.5, rp, 0.0)
                    raise AssertionError((fname, bad_v))
                except ec:
                    subcases += 1
        ok_seg = UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=ok_v, wrist_end_xyz=ok_v)
        for bad_y, ec in ((True, TypeError), ("90", TypeError), (None, TypeError), ([0.0], TypeError), (float("nan"), ValueError), (float("inf"), ValueError), (float("-inf"), ValueError), (10**400, ValueError)):
            try:
                _evaluate_upper_limb_segment(ok_seg, "L", 0.5, ok_v, bad_y)
                raise AssertionError(bad_y)
            except ec:
                subcases += 1
        assert subcases == 68
        return {"subcases": subcases}

    def test_t16() -> Dict[str, Any]:
        ok3, v3 = ((0.0, 0.0, 0.0),) * 3, (0.0, 0.0, 1.0)
        conflicts = (
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=None, fk_end_deg=ok3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=None), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=(v3, v3), fk_end_deg=ok3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=[v3, v3, v3], fk_end_deg=ok3), TypeError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, wrist_start_xyz=v3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, wrist_end_xyz=v3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, rotation_start_deg=v3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, rotation_end_deg=v3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, pole_start_xyz=v3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, pole_end_xyz=v3), ValueError),
            (UpperLimbSegment("FK", 0.0, 1.0, fk_start_deg=ok3, fk_end_deg=ok3, position_space="ROOT_LOCAL"), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=None, wrist_end_xyz=v3), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=None), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, fk_start_deg=ok3, wrist_start_xyz=v3, wrist_end_xyz=v3), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, fk_end_deg=ok3, wrist_start_xyz=v3, wrist_end_xyz=v3), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, rotation_start_deg=v3, rotation_end_deg=None), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, rotation_start_deg=None, rotation_end_deg=v3), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, pole_start_xyz=v3, pole_end_xyz=None), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, pole_start_xyz=None, pole_end_xyz=v3), ValueError),
        )
        for seg, ec in conflicts:
            try:
                _evaluate_upper_limb_segment(seg, "L", 0.5, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(seg)
            except ec:
                pass
        return {"subcases": len(conflicts)}

    def test_t17() -> Dict[str, Any]:
        v3 = (0.0, 0.0, 1.0)
        temporal_bad = (
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), -0.1, ValueError),
            (UpperLimbSegment("IK", 0.0, 0.0, wrist_start_xyz=v3, wrist_end_xyz=v3), 0.0, ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), float("nan"), ValueError),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), True, TypeError),
            (UpperLimbSegment("IK", 1e308, 1e308, wrist_start_xyz=v3, wrist_end_xyz=v3), 1.0, ValueError),
            (UpperLimbSegment("IK", 1e16, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3), 1e16, ValueError),
        )
        for seg, tv, ec in temporal_bad:
            try:
                _evaluate_upper_limb_segment(seg, "L", tv, (0.0, 0.0, 0.0), 0.0)
                raise AssertionError(tv)
            except ec:
                pass
        for seg, rp, ry in (
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(1.5e308, 1.5e308, 0.0), wrist_end_xyz=(1.5e308, 1.5e308, 0.0), position_space="ROOT_LOCAL"), (0.0, 0.0, 0.0), 45.0),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=(1e308, 0.0, 0.0), wrist_end_xyz=(1e308, 0.0, 0.0), position_space="ROOT_LOCAL"), (1e308, 0.0, 0.0), 0.0),
            (UpperLimbSegment("IK", 0.0, 1.0, wrist_start_xyz=v3, wrist_end_xyz=v3, pole_start_xyz=(1e308, 0.0, 0.0), pole_end_xyz=(1e308, 0.0, 0.0), position_space="ROOT_LOCAL"), (1e308, 0.0, 0.0), 0.0),
        ):
            try:
                _evaluate_upper_limb_segment(seg, "L", 0.5, rp, ry)
                raise AssertionError(seg)
            except ValueError:
                pass
        return {"subcases": 9}

    def test_t18() -> Dict[str, Any]:
        rot = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0))
        fk_seg = UpperLimbSegment("FK", 1.0, 2.0, fk_start_deg=rot, fk_end_deg=rot)
        ik_seg = UpperLimbSegment("IK", 1.0, 2.0, wrist_start_xyz=(0.2, 0.4, 1.1), wrist_end_xyz=(0.4, 0.6, 1.3), rotation_start_deg=(1.0, 2.0, 3.0), rotation_end_deg=(4.0, 5.0, 6.0), pole_start_xyz=(-0.1, -0.2, 1.0), pole_end_xyz=(-0.2, -0.3, 1.1), position_space="ROOT_LOCAL")
        try:
            fk_seg.mode = "IK"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except (FrozenInstanceError, AttributeError):
            pass
        _, d1 = _evaluate_upper_limb_segment(fk_seg, "L", 1.5, (2.0, -3.0, 0.5), 25.0)
        snap = dict(d1)
        d1["hand.L"] = (999.0, 999.0, 999.0)
        d1.clear()
        _, d2 = _evaluate_upper_limb_segment(fk_seg, "L", 1.5, (2.0, -3.0, 0.5), 25.0)
        assert d2 == snap
        ti1, _ = _evaluate_upper_limb_segment(ik_seg, "R", 1.5, (2.0, -3.0, 0.5), 25.0)
        s_xyz, s_rot, s_p = ti1.world_xyz, ti1.rotation_deg, ti1.pole_hint_world_xyz
        ti1.world_xyz = (999.0, 999.0, 999.0)
        ti2, _ = _evaluate_upper_limb_segment(ik_seg, "R", 1.5, (2.0, -3.0, 0.5), 25.0)
        assert (ti2.world_xyz, ti2.rotation_deg, ti2.pole_hint_world_xyz) == (s_xyz, s_rot, s_p)
        return {"ok": True}

    tests = (
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
    )
    for tid, title, fn in tests:
        detail = fn()
        records.append({"id": tid, "title": title, "status": "PASS", **detail})

    return {"passed": len(records), "failed": 0, "total": 18, "tests": records}


def _run_10d4_repeat_cleanup_contract() -> Dict[str, Any]:
    import bpy
    from src.character.builder import build_character
    from src.config import PipelineConfig
    from src.motion.framework import MotionPlanner, StartStopWalkAction, create_initial_motion_state
    from src.motion.run_cycle import RunAction
    from src.motion.upper_limb_trajectory import UpperLimbSegment
    from src.rig.builder import bind_character_to_rig, build_rig
    from src.scene.builder import setup_scene

    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    setup_scene(cfg)
    parts = build_character(cfg)
    root = bpy.data.objects["CharacterRoot"]
    root.location = (0.0, -8.0, 0.0)
    arm = build_rig(cfg, character_root=root)
    bind_character_to_rig(arm, parts)
    bpy.context.view_layer.update()

    # Pass 1: 252 frames bilateral IK with ElbowPole + HandRotation
    sys.path.insert(0, str(REPO_ROOT / "docs" / "evidence" / "10-d" / "10-d-5" / "centralized_verification"))
    import common_helpers as ch
    vr = ch.load_vr()
    wl0, pl0 = (-0.28, 0.24, 1.24), (-0.36, -0.22, 1.18)
    wl1, pl1 = (-0.36, 0.34, 1.32), (-0.40, -0.26, 1.20)
    wr0, pr0 = (0.28, 0.24, 1.24), (0.36, -0.22, 1.18)
    wr1, pr1 = (0.36, 0.34, 1.32), (0.40, -0.26, 1.20)
    rot_l0 = vr._compute_hand_world_rot_for_ik_keypose(arm, "L", wl0, pl0, (0.0, 0.0, 0.0))
    rot_l1 = vr._compute_hand_world_rot_for_ik_keypose(arm, "L", wl1, pl1, (8.0, 0.0, 0.0))
    rot_r0 = vr._compute_hand_world_rot_for_ik_keypose(arm, "R", wr0, pr0, (0.0, 0.0, 0.0))
    rot_r1 = vr._compute_hand_world_rot_for_ik_keypose(arm, "R", wr1, pr1, (8.0, 0.0, 0.0))

    n_pass1 = 252
    dur1 = (n_pass1 - 1) / 24.0
    ik_l = (
        UpperLimbSegment("IK", 0.0, dur1, wrist_start_xyz=wl0, wrist_end_xyz=wl1, pole_start_xyz=pl0, pole_end_xyz=pl1, rotation_start_deg=rot_l0, rotation_end_deg=rot_l1, position_space="ROOT_LOCAL", clamp_reach=False),
    )
    ik_r = (
        UpperLimbSegment("IK", 0.0, dur1, wrist_start_xyz=wr0, wrist_end_xyz=wr1, pole_start_xyz=pr0, pole_end_xyz=pr1, rotation_start_deg=rot_r0, rotation_end_deg=rot_r1, position_space="ROOT_LOCAL", clamp_reach=False),
    )
    planner1 = MotionPlanner(config=cfg, armature_obj=arm, upper_limb_L=ik_l, upper_limb_R=ik_r, sequence_duration_sec=dur1)
    planner1.add_action(StartStopWalkAction())
    planner1.add_action(RunAction(cycles=2))
    planner1.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=(0.0, -8.0, 0.0)))

    pass1_action_names = {}
    for cname in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
        cobj = bpy.data.objects[cname]
        assert cobj.animation_data is not None and cobj.animation_data.action is not None
        pass1_action_names[cname] = cobj.animation_data.action.name

    # Pass 2: Shorter 204-frame run with upper limbs disabled (None) -> no stale frames 205..252 survive cleanup
    planner2 = MotionPlanner(config=cfg, armature_obj=arm)
    planner2.add_action(StartStopWalkAction())
    planner2.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=(0.0, -8.0, 0.0)))

    pass2_frames = {}
    expected_frames = set(range(1, 205))
    for cname in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
        cobj = bpy.data.objects[cname]
        ad = cobj.animation_data
        f_sets = []
        if ad is not None and ad.action is not None:
            for lyr in getattr(ad.action, "layers", []):
                for strip in getattr(lyr, "strips", []):
                    for b in getattr(strip, "channelbags", []):
                        for fc in b.fcurves:
                            f_sets.append({int(round(kp.co[0])) for kp in fc.keyframe_points})
        assert f_sets and all(fs == expected_frames for fs in f_sets), f"Stale frames on {cname}: {f_sets}"
        pass2_frames[cname] = {"fcurves": len(f_sets), "frame_min": 1, "frame_max": 204}

    bpy.context.scene.frame_set(100)
    bpy.context.view_layer.update()
    inf_zero = {
        cname: float(arm.pose.bones[bname].constraints[cname].influence)
        for cname, bname in (("ArmIK.L", "forearm.L"), ("ArmIK.R", "forearm.R"), ("HandRotation.L", "hand.L"), ("HandRotation.R", "hand.R"))
    }
    assert all(v == 0.0 for v in inf_zero.values()), inf_zero
    return {"pass1_frames": n_pass1, "pass1_actions": pass1_action_names, "pass2_cleaned": pass2_frames, "pass2_frame100_influences": inf_zero}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    r_10d2 = _run_10d2_migrated()
    r_10d3 = _run_10d3_migrated()
    r_10d4 = _run_10d4_repeat_cleanup_contract()
    summary = {
        "git_head": head,
        "10d2_migrated_upper_limb_progress": r_10d2,
        "10d3_migrated_upper_limb_segment": r_10d3,
        "10d4_repeat_cleanup_and_influence_clear": r_10d4,
        "all_passed": True,
    }
    out_path = OUT_DIR / "migrated_10d_production_report.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"MIGRATED_PROD_OK 10d2={r_10d2['passed']}/12 10d3={r_10d3['passed']}/18 (T15=68/68) 10d4_cleanup=PASS",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
