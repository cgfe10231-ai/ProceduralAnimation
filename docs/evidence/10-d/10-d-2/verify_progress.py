"""Task 10-d-2 targeted mathematical verification for _evaluate_upper_limb_progress()."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[4]
SOURCE_PATH = REPO_ROOT / "src" / "motion" / "terrain_walk.py"
EVIDENCE_DIR = Path(__file__).resolve().parent
RESULTS_PATH = EVIDENCE_DIR / "results.json"
FUNC_NAME = "_evaluate_upper_limb_progress"


def _extract_target_function() -> Tuple[Callable[[float, float, float], Tuple[float, float]], Dict[str, Any]]:
    source_bytes = SOURCE_PATH.read_bytes()
    source_text = source_bytes.decode("utf-8")
    tree = ast.parse(source_text, filename=str(SOURCE_PATH))

    target_node = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == FUNC_NAME:
            target_node = node
            break
    if target_node is None:
        raise RuntimeError(f"{FUNC_NAME} not found in {SOURCE_PATH}")

    extracted_src = ast.get_source_segment(source_text, target_node)
    if not extracted_src:
        lines = source_text.splitlines()
        extracted_src = "\n".join(lines[target_node.lineno - 1 : target_node.end_lineno])

    extracted_sha256 = hashlib.sha256(extracted_src.encode("utf-8")).hexdigest()
    file_sha256 = hashlib.sha256(source_bytes).hexdigest()

    namespace: Dict[str, Any] = {
        "math": math,
        "List": List,
        "Tuple": Tuple,
    }
    code = compile(extracted_src, str(SOURCE_PATH), "exec")
    exec(code, namespace, namespace)
    fn = namespace[FUNC_NAME]

    git_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPO_ROOT, text=True
    ).strip()
    git_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()
    git_blob = subprocess.check_output(
        ["git", "hash-object", "src/motion/terrain_walk.py"], cwd=REPO_ROOT, text=True
    ).strip()

    meta = {
        "branch": git_branch,
        "head": git_head,
        "terrain_walk_blob": git_blob,
        "terrain_walk_sha256": file_sha256,
        "extracted_function": FUNC_NAME,
        "extracted_source_lines": [target_node.lineno, target_node.end_lineno],
        "extracted_source_sha256": extracted_sha256,
        "isolated_dependencies": ["math", "List", "Tuple"],
    }
    return fn, meta


def main() -> int:
    fn, source_meta = _extract_target_function()
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

    # T01: Before start and at start
    def test_t01() -> Dict[str, Any]:
        cases = [
            (0.0, 2.0, 3.0),
            (0.5, 2.0, 3.0),
            (1.999999, 2.0, 3.0),
            (2.0, 2.0, 3.0),
            (0.0, 0.0, 1.5),
            (-0.0, 0.0, 1.5),
        ]
        subcases = []
        for t, s, d in cases:
            out = fn(t, s, d)
            assert out == (0.0, 0.0) and isinstance(out, tuple), (t, s, d, out)
            assert not math.copysign(1.0, out[0]) < 0.0 and not math.copysign(1.0, out[1]) < 0.0
            subcases.append({"input": [t, s, d], "output": list(out)})
        return {"subcases": subcases}

    # T02: At end and after end
    def test_t02() -> Dict[str, Any]:
        cases = [
            (5.0, 2.0, 3.0),
            (1.5, 0.0, 1.5),
            (5.000001, 2.0, 3.0),
            (100.0, 2.0, 3.0),
        ]
        subcases = []
        for t, s, d in cases:
            out = fn(t, s, d)
            assert out == (1.0, 1.0) and isinstance(out, tuple), (t, s, d, out)
            subcases.append({"input": [t, s, d], "output": list(out)})
        return {"subcases": subcases}

    # T03: Quintic polynomial values at u=0.25, 0.5, 0.75
    def test_t03() -> Dict[str, Any]:
        expected = [
            (0.25, 0.103515625),
            (0.5, 0.5),
            (0.75, 0.896484375),
        ]
        subcases = []
        max_abs_err = 0.0
        for target_u, exp_h in expected:
            for s, d in ((0.0, 1.0), (1.0, 4.0)):
                t = s + target_u * d
                u, h = fn(t, s, d)
                u_err = abs(u - target_u)
                h_err = abs(h - exp_h)
                max_abs_err = max(max_abs_err, u_err, h_err)
                assert u_err <= 1e-12 and h_err <= 1e-12, (t, s, d, u, h, exp_h)
                subcases.append(
                    {
                        "input": [t, s, d],
                        "u": u,
                        "expected_u": target_u,
                        "h": h,
                        "expected_h": exp_h,
                        "abs_err_h": h_err,
                    }
                )
        return {"max_abs_err": max_abs_err, "tolerance": 1e-12, "subcases": subcases}

    # T04: Monotonicity and range over 10001 samples on [0, 1]
    def test_t04() -> Dict[str, Any]:
        sample_count = 10001
        intervals = [
            ("normalized_0_1", 0.0, 1.0),
            ("shifted_1.25_2.5", 1.25, 2.5),
        ]
        subcases = []
        for label, s, d in intervals:
            prev_u = -1.0
            prev_h = -1.0
            min_u, max_u = float("inf"), float("-inf")
            min_h, max_h = float("inf"), float("-inf")
            for i in range(sample_count):
                alpha = i / (sample_count - 1)
                t = s + alpha * d
                u, h = fn(t, s, d)
                assert math.isfinite(u) and math.isfinite(h), (i, u, h)
                assert 0.0 <= u <= 1.0 and 0.0 <= h <= 1.0, (i, u, h)
                assert u >= prev_u and h >= prev_h, (i, prev_u, u, prev_h, h)
                prev_u, prev_h = u, h
                min_u, max_u = min(min_u, u), max(max_u, u)
                min_h, max_h = min(min_h, h), max(max_h, h)
            subcases.append(
                {
                    "interval": label,
                    "sample_count": sample_count,
                    "min_u": min_u,
                    "max_u": max_u,
                    "min_h": min_h,
                    "max_h": max_h,
                }
            )
        return {"subcases": subcases}

    # T05: Analytic endpoint derivative contract + finite-difference convergence
    def test_t05() -> Dict[str, Any]:
        # Analytic contract of h(u) = 10*u**3 - 15*u**4 + 6*u**5:
        # h'(u)  = 30 * u**2 * (1 - u)**2
        # h''(u) = 60 * u * (1 - u) * (1 - 2*u)
        def h_analytic(u: float) -> float:
            return 10.0 * u**3 - 15.0 * u**4 + 6.0 * u**5

        def dh_analytic(u: float) -> float:
            return 30.0 * (u**2) * ((1.0 - u) ** 2)

        def d2h_analytic(u: float) -> float:
            return 60.0 * u * (1.0 - u) * (1.0 - 2.0 * u)

        analytic_endpoints = {
            "u0_h": h_analytic(0.0),
            "u0_dh": dh_analytic(0.0),
            "u0_d2h": d2h_analytic(0.0),
            "u1_h": h_analytic(1.0),
            "u1_dh": dh_analytic(1.0),
            "u1_d2h": d2h_analytic(1.0),
        }
        assert analytic_endpoints == {
            "u0_h": 0.0,
            "u0_dh": 0.0,
            "u0_d2h": 0.0,
            "u1_h": 1.0,
            "u1_dh": 0.0,
            "u1_d2h": 0.0,
        }, analytic_endpoints

        # Verify piecewise equivalence against exact mathematical quintic across [0, 1]
        from fractions import Fraction

        max_poly_diff = 0.0
        for i in range(101):
            u_frac = Fraction(i, 100)
            h_exact = float(10 * u_frac**3 - 15 * u_frac**4 + 6 * u_frac**5)
            _, h_fn = fn(i / 100.0, 0.0, 1.0)
            diff = abs(h_fn - h_exact)
            max_poly_diff = max(max_poly_diff, diff)
            assert diff <= 1e-12, (i / 100.0, h_fn, h_exact, diff)

        steps = [1e-3, 1e-4, 1e-5]
        convergence = []
        for delta in steps:
            _, h0 = fn(0.0, 0.0, 1.0)
            _, hd1 = fn(delta, 0.0, 1.0)
            _, hd2 = fn(2.0 * delta, 0.0, 1.0)
            d1_start = (hd1 - h0) / delta
            d2_start = (hd2 - 2.0 * hd1 + h0) / (delta**2)

            _, h1 = fn(1.0, 0.0, 1.0)
            _, hm1 = fn(1.0 - delta, 0.0, 1.0)
            _, hm2 = fn(1.0 - 2.0 * delta, 0.0, 1.0)
            d1_end = (h1 - hm1) / delta
            d2_end = (h1 - 2.0 * hm1 + hm2) / (delta**2)

            convergence.append(
                {
                    "step": delta,
                    "d1_start_abs_err": abs(d1_start),
                    "d2_start_abs_err": abs(d2_start),
                    "d1_end_abs_err": abs(d1_end),
                    "d2_end_abs_err": abs(d2_end),
                }
            )

        # Verify monotonic error decrease with smaller step size and threshold at 1e-5
        for idx in range(1, len(convergence)):
            prev_c, cur_c = convergence[idx - 1], convergence[idx]
            for key in (
                "d1_start_abs_err",
                "d2_start_abs_err",
                "d1_end_abs_err",
                "d2_end_abs_err",
            ):
                assert cur_c[key] < prev_c[key], (key, prev_c, cur_c)

        finest = convergence[-1]
        assert finest["d1_start_abs_err"] < 1e-6, finest
        assert finest["d1_end_abs_err"] < 1e-6, finest
        assert finest["d2_start_abs_err"] < 1e-2, finest
        assert finest["d2_end_abs_err"] < 1e-2, finest

        return {
            "analytic_endpoints": analytic_endpoints,
            "max_piecewise_polynomial_diff": max_poly_diff,
            "convergence": convergence,
        }

    # T06: Reject invalid types with TypeError
    def test_t06() -> Dict[str, Any]:
        bad_types: List[Tuple[str, Any]] = [
            ("bool_true", True),
            ("bool_false", False),
            ("none", None),
            ("str", "1.0"),
            ("list", [1.0]),
            ("complex", 1.0 + 0j),
        ]
        param_names = ("time_sec", "start_time_sec", "duration_sec")
        subcases = []
        for p_idx, p_name in enumerate(param_names):
            for label, bad_val in bad_types:
                args = [1.0, 1.0, 1.0]
                args[p_idx] = bad_val
                raised = None
                try:
                    fn(*args)
                except Exception as exc:
                    raised = type(exc).__name__
                    assert type(exc) is TypeError, (p_name, label, raised)
                assert raised == "TypeError", (p_name, label, raised)
                subcases.append({"param": p_name, "bad_type": label, "raised": raised})
        return {"subcases_count": len(subcases), "subcases": subcases}

    # T07: Reject non-finite values with ValueError
    def test_t07() -> Dict[str, Any]:
        bad_vals: List[Tuple[str, float]] = [
            ("nan", float("nan")),
            ("pos_inf", float("inf")),
            ("neg_inf", float("-inf")),
        ]
        param_names = ("time_sec", "start_time_sec", "duration_sec")
        subcases = []
        for p_idx, p_name in enumerate(param_names):
            for label, bad_val in bad_vals:
                args = [1.0, 1.0, 1.0]
                args[p_idx] = bad_val
                raised = None
                try:
                    fn(*args)
                except Exception as exc:
                    raised = type(exc).__name__
                    assert type(exc) is ValueError, (p_name, label, raised)
                assert raised == "ValueError", (p_name, label, raised)
                subcases.append({"param": p_name, "bad_value": label, "raised": raised})
        return {"subcases_count": len(subcases), "subcases": subcases}

    # T08: Reject negative times and zero/negative duration with ValueError
    def test_t08() -> Dict[str, Any]:
        cases = [
            ("neg_time_small", -1e-6, 0.0, 1.0),
            ("neg_time_int", -1, 0.0, 1.0),
            ("neg_start_small", 0.0, -1e-6, 1.0),
            ("neg_start_float", 1.0, -2.5, 1.0),
            ("zero_duration_int", 0.5, 0.0, 0),
            ("zero_duration_float", 0.5, 0.0, 0.0),
            ("neg_zero_duration", 0.5, 0.0, -0.0),
            ("neg_duration_small", 0.5, 0.0, -1e-6),
            ("neg_duration_float", 0.5, 0.0, -2.0),
        ]
        subcases = []
        for label, t, s, d in cases:
            raised = None
            try:
                fn(t, s, d)
            except Exception as exc:
                raised = type(exc).__name__
                assert type(exc) is ValueError, (label, raised)
            assert raised == "ValueError", (label, raised)
            subcases.append({"case": label, "input": [t, s, d], "raised": raised})
        return {"subcases": subcases}

    # T09: Numerical limits (int->float overflow, end_time overflow, precision loss)
    def test_t09() -> Dict[str, Any]:
        cases: List[Tuple[str, Any, Any, Any, str]] = [
            ("huge_int_time", 10**400, 0.0, 1.0, "10**400"),
            ("huge_int_start", 0.0, 10**400, 1.0, "10**400"),
            ("huge_int_duration", 0.0, 0.0, 10**400, "10**400"),
            ("end_time_overflow", 1.0, 1e308, 1e308, "1e308+1e308->inf"),
            ("precision_loss_1e16_1", 1e16, 1e16, 1.0, "1e16+1.0==1e16"),
            ("precision_loss_1_1e_16", 1.0, 1.0, 1e-16, "1.0+1e-16==1.0"),
        ]
        subcases = []
        for label, t, s, d, note in cases:
            raised = None
            try:
                fn(t, s, d)
            except Exception as exc:
                raised = type(exc).__name__
                assert type(exc) is ValueError, (label, raised)
            assert raised == "ValueError", (label, raised)
            subcases.append({"case": label, "note": note, "raised": raised})
        return {"subcases": subcases}

    # T10: Independent left/right start times
    def test_t10() -> Dict[str, Any]:
        t, d = 2.5, 2.0
        left = fn(t, 1.0, d)
        right = fn(t, 2.0, d)
        assert left == (0.75, 0.896484375), left
        assert right == (0.25, 0.103515625), right
        assert left != right
        return {"time_sec": t, "duration_sec": d, "left": list(left), "right": list(right)}

    # T11: Independent left/right durations
    def test_t11() -> Dict[str, Any]:
        t, s = 2.0, 1.0
        left = fn(t, s, 2.0)
        right = fn(t, s, 4.0)
        assert left == (0.5, 0.5), left
        assert right == (0.25, 0.103515625), right
        assert left != right
        return {"time_sec": t, "start_time_sec": s, "left": list(left), "right": list(right)}

    # T12: Statelessness & determinism across interleaved/repeated calls
    def test_t12() -> Dict[str, Any]:
        probe_a = (2.37, 1.2, 2.6)
        probe_b = (4.15, 3.0, 1.8)
        baseline_a = fn(*probe_a)
        baseline_b = fn(*probe_b)

        for _ in range(50):
            assert fn(*probe_a) == baseline_a
            assert fn(*probe_b) == baseline_b
            assert fn(0.2, 1.2, 2.6) == (0.0, 0.0)
            assert fn(9.9, 3.0, 1.8) == (1.0, 1.0)
            try:
                fn(-1.0, 0.0, 1.0)
            except ValueError:
                pass
            try:
                fn(True, 0.0, 1.0)
            except TypeError:
                pass

        after_a = fn(*probe_a)
        after_b = fn(*probe_b)
        assert after_a == baseline_a and after_b == baseline_b
        return {
            "probe_a": {"input": list(probe_a), "baseline": list(baseline_a), "after": list(after_a)},
            "probe_b": {"input": list(probe_b), "baseline": list(baseline_b), "after": list(after_b)},
            "interleaved_cycles": 50,
        }

    run_test("T01", "开始前及开始时边界", test_t01)
    run_test("T02", "结束时及结束后边界", test_t02)
    run_test("T03", "五次插值数学正确性", test_t03)
    run_test("T04", "进度单调性与值域", test_t04)
    run_test("T05", "端点解析导数与有限差分收敛", test_t05)
    run_test("T06", "非法类型拒绝", test_t06)
    run_test("T07", "非有限数值拒绝", test_t07)
    run_test("T08", "时间与持续时间范围拒绝", test_t08)
    run_test("T09", "数值溢出与精度退化拒绝", test_t09)
    run_test("T10", "左右独立开始时间", test_t10)
    run_test("T11", "左右独立持续时间", test_t11)
    run_test("T12", "重复与交替调用无状态性", test_t12)

    passed = sum(1 for r in records if r["status"] == "PASS")
    failed = sum(1 for r in records if r["status"] != "PASS")
    exit_code = 0 if failed == 0 and passed == 12 else 1

    payload = {
        "task": "TASK 10-d-2 — TARGETED VERIFICATION",
        "command": " ".join([sys.executable, "-B", "docs/evidence/10-d/10-d-2/verify_progress.py"]),
        "exit_code": exit_code,
        "source_baseline": source_meta,
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
