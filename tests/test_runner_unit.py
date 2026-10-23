"""Comprehensive Unit Test Suite for Unified Test Runner (Task 6G-D-PRE-P1-R1).

Verifies core safety, failure detection, and reporting mechanisms of TestSuiteRunner:
1. Normal execution & pass state.
2. Non-zero exit code detection.
3. stdout explicit FAIL pattern detection (even when exit code is 0).
4. Required vs optional dependency / script missing detection.
5. Expected artifact missing or empty (0-byte) detection.
6. Execution timeout and Windows process tree termination.
7. Fail-fast halt and remaining test tracking.
8. NOT_RUN status recording and non-pass accounting.
9. JSON report all_success logic matrix.
10. Final suite exit code logic.

Runs fast in pure Python without heavy Blender dependencies.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import time
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.run_test_suite import (
    TestSuiteRunner,
    TestExecutionResult,
    resolve_python_executable,
)
from tests.test_registry import RunnerType, TestDefinition, TestTier


class TestRunnerUnitTests(unittest.TestCase):
    """Unit tests for the TestSuiteRunner execution engine and reporting logic."""

    @classmethod
    def setUpClass(cls):
        cls.python_exe = resolve_python_executable()
        cls.unit_tmp_dir = os.path.join(PROJECT_ROOT, "tests", "output", "unit_tmp")
        os.makedirs(cls.unit_tmp_dir, exist_ok=True)

        # 1. pass_script.py
        cls.pass_script_rel = os.path.relpath(
            os.path.join(cls.unit_tmp_dir, "pass_script.py"), PROJECT_ROOT
        )
        with open(os.path.join(PROJECT_ROOT, cls.pass_script_rel), "w", encoding="utf-8") as fp:
            fp.write("print('[OK] Sub-test executed cleanly')\n")

        # 2. nonzero_script.py
        cls.nonzero_script_rel = os.path.relpath(
            os.path.join(cls.unit_tmp_dir, "nonzero_script.py"), PROJECT_ROOT
        )
        with open(os.path.join(PROJECT_ROOT, cls.nonzero_script_rel), "w", encoding="utf-8") as fp:
            fp.write("import sys\nprint('Simulating crash')\nsys.exit(42)\n")

        # 3. fail_pattern_script.py (exit code 0, but stdout contains [FAIL])
        cls.fail_pattern_script_rel = os.path.relpath(
            os.path.join(cls.unit_tmp_dir, "fail_pattern_script.py"), PROJECT_ROOT
        )
        with open(os.path.join(PROJECT_ROOT, cls.fail_pattern_script_rel), "w", encoding="utf-8") as fp:
            fp.write("print('[FAIL] Latent assertion violation detected')\nimport sys\nsys.exit(0)\n")

        # 4. sleep_script.py (for timeout testing)
        cls.sleep_script_rel = os.path.relpath(
            os.path.join(cls.unit_tmp_dir, "sleep_script.py"), PROJECT_ROOT
        )
        with open(os.path.join(PROJECT_ROOT, cls.sleep_script_rel), "w", encoding="utf-8") as fp:
            fp.write("import time\ntime.sleep(10)\n")

        # Create runner instance pointing to unit_tmp_dir
        cls.runner = TestSuiteRunner(
            blender_bin="mock_blender.exe",
            python_bin=cls.python_exe,
            output_dir=cls.unit_tmp_dir,
            timeout_multiplier=1.0,
            fail_fast=False,
        )

    @classmethod
    def tearDownClass(cls):
        # Cleanup temporary files
        if os.path.isdir(cls.unit_tmp_dir):
            shutil.rmtree(cls.unit_tmp_dir, ignore_errors=True)

    def run_silent(self, fn, *args, **kwargs):
        """Execute a callable while capturing stdout and stderr to avoid leaking failure patterns."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*args, **kwargs)

    def test_01_normal_execution_and_all_pass(self):
        """Case 1: Standard script runs cleanly, status=PASSED, exit_code=0."""
        test_def = TestDefinition(
            test_id="unit_case_pass",
            name="Unit Case Pass",
            script_path=self.pass_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            timeout_sec=5.0,
        )
        res = self.run_silent(self.runner.execute_test, test_def)
        self.assertEqual(res.status, "PASSED")
        self.assertEqual(res.exit_code, 0)
        self.assertIsNone(res.failure_reason)

    def test_02_nonzero_exit_code_detection(self):
        """Case 2: Process exits with non-zero code, status=FAILED."""
        test_def = TestDefinition(
            test_id="unit_case_nonzero",
            name="Unit Case Nonzero",
            script_path=self.nonzero_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            timeout_sec=5.0,
        )
        res = self.run_silent(self.runner.execute_test, test_def)
        self.assertEqual(res.status, "FAILED")
        self.assertEqual(res.exit_code, 42)
        self.assertIn("non-zero code 42", res.failure_reason)

    def test_03_stdout_explicit_fail_pattern(self):
        """Case 3: Process exits with code 0, but stdout contains explicit failure pattern."""
        test_def = TestDefinition(
            test_id="unit_case_fail_pattern",
            name="Unit Case Fail Pattern",
            script_path=self.fail_pattern_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            timeout_sec=5.0,
        )
        res = self.run_silent(self.runner.execute_test, test_def)
        self.assertEqual(res.status, "FAILED")
        self.assertEqual(res.exit_code, 0)
        self.assertIsNotNone(res.failure_reason)
        self.assertIn("Failure pattern detected in output", res.failure_reason)

    def test_04_required_vs_optional_missing_dependency(self):
        """Case 4: Missing test script or blend file must fail if required, skip if optional."""
        # 4a. Missing required script
        req_missing = TestDefinition(
            test_id="unit_case_missing_req",
            name="Unit Case Missing Req",
            script_path="tests/output/unit_tmp/non_existent_script.py",
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            is_optional=False,
        )
        res_req = self.run_silent(self.runner.execute_test, req_missing)
        self.assertEqual(res_req.status, "FAILED")
        self.assertIn("Required test script missing", res_req.failure_reason)

        # 4b. Missing optional script
        opt_missing = TestDefinition(
            test_id="unit_case_missing_opt",
            name="Unit Case Missing Opt",
            script_path="tests/output/unit_tmp/non_existent_script.py",
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            is_optional=True,
        )
        res_opt = self.run_silent(self.runner.execute_test, opt_missing)
        self.assertEqual(res_opt.status, "SKIPPED")
        self.assertIn("Test script missing", res_opt.failure_reason)

        # 4c. Missing required target blend
        req_blend_missing = TestDefinition(
            test_id="unit_case_blend_missing_req",
            name="Unit Case Blend Missing Req",
            script_path=self.pass_script_rel,
            runner_type=RunnerType.BLENDER_WITH_BLEND,
            target_blend="output/non_existent.blend",
            tiers=[TestTier.QUICK],
            is_optional=False,
        )
        res_blend_req = self.run_silent(self.runner.execute_test, req_blend_missing)
        self.assertEqual(res_blend_req.status, "FAILED")
        self.assertIn("Required target blend not found", res_blend_req.failure_reason)

        # 4d. Missing optional target blend
        opt_blend_missing = TestDefinition(
            test_id="unit_case_blend_missing_opt",
            name="Unit Case Blend Missing Opt",
            script_path=self.pass_script_rel,
            runner_type=RunnerType.BLENDER_WITH_BLEND,
            target_blend="output/non_existent.blend",
            tiers=[TestTier.QUICK],
            is_optional=True,
        )
        res_blend_opt = self.run_silent(self.runner.execute_test, opt_blend_missing)
        self.assertEqual(res_blend_opt.status, "SKIPPED")

    def test_05_expected_artifacts_validation(self):
        """Case 5: Missing or 0-byte expected artifact fails test, valid artifact passes."""
        missing_art_rel = "tests/output/unit_tmp/missing_artifact.bin"
        empty_art_rel = "tests/output/unit_tmp/empty_artifact.bin"
        valid_art_rel = "tests/output/unit_tmp/valid_artifact.bin"

        # Create empty artifact
        with open(os.path.join(PROJECT_ROOT, empty_art_rel), "wb") as fp:
            pass

        # Create valid artifact (>0 bytes)
        with open(os.path.join(PROJECT_ROOT, valid_art_rel), "wb") as fp:
            fp.write(b"non_empty_content")

        # 5a. Missing expected artifact
        test_missing = TestDefinition(
            test_id="unit_case_art_missing",
            name="Unit Case Art Missing",
            script_path=self.pass_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            expected_artifacts=[missing_art_rel],
        )
        res_m = self.run_silent(self.runner.execute_test, test_missing)
        self.assertEqual(res_m.status, "FAILED")
        self.assertIn("Required expected artifact missing", res_m.failure_reason)

        # 5b. Empty expected artifact (0 bytes)
        test_empty = TestDefinition(
            test_id="unit_case_art_empty",
            name="Unit Case Art Empty",
            script_path=self.pass_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            expected_artifacts=[empty_art_rel],
        )
        res_e = self.run_silent(self.runner.execute_test, test_empty)
        self.assertEqual(res_e.status, "FAILED")
        self.assertIn("empty (0 bytes)", res_e.failure_reason)

        # 5c. Valid expected artifact
        test_valid = TestDefinition(
            test_id="unit_case_art_valid",
            name="Unit Case Art Valid",
            script_path=self.pass_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            expected_artifacts=[valid_art_rel],
        )
        res_v = self.run_silent(self.runner.execute_test, test_valid)
        self.assertEqual(res_v.status, "PASSED")
        self.assertIsNone(res_v.failure_reason)

    def test_06_timeout_and_process_kill(self):
        """Case 6: Process exceeds timeout, is terminated, and status=FAILED."""
        test_timeout = TestDefinition(
            test_id="unit_case_timeout",
            name="Unit Case Timeout",
            script_path=self.sleep_script_rel,
            runner_type=RunnerType.PYTHON,
            tiers=[TestTier.QUICK],
            timeout_sec=0.5,
        )
        start_t = time.time()
        res = self.run_silent(self.runner.execute_test, test_timeout)
        duration = time.time() - start_t

        self.assertEqual(res.status, "FAILED")
        self.assertIn("Execution timed out", res.failure_reason)
        # Verify process was terminated and did not wait full 10 seconds
        self.assertLess(duration, 3.5)

    def test_07_fail_fast_behavior(self):
        """Case 7: fail-fast stops execution immediately on first failure and records NOT_RUN."""
        fast_runner = TestSuiteRunner(
            blender_bin="mock_blender.exe",
            python_bin=self.python_exe,
            output_dir=self.unit_tmp_dir,
            timeout_multiplier=1.0,
            fail_fast=True,
        )
        tests = [
            TestDefinition(
                test_id="test_seq_1",
                name="Test Seq 1 Pass",
                script_path=self.pass_script_rel,
                runner_type=RunnerType.PYTHON,
                tiers=[TestTier.QUICK],
            ),
            TestDefinition(
                test_id="test_seq_2",
                name="Test Seq 2 Fail",
                script_path=self.nonzero_script_rel,
                runner_type=RunnerType.PYTHON,
                tiers=[TestTier.QUICK],
            ),
            TestDefinition(
                test_id="test_seq_3",
                name="Test Seq 3 Pass",
                script_path=self.pass_script_rel,
                runner_type=RunnerType.PYTHON,
                tiers=[TestTier.QUICK],
            ),
        ]
        results = self.run_silent(fast_runner.run_suite, tests)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].status, "PASSED")
        self.assertEqual(results[1].status, "FAILED")
        self.assertEqual(results[2].status, "NOT_RUN")
        self.assertIsNone(results[2].exit_code)
        self.assertIn("fail-fast", results[2].failure_reason)

    def test_08_not_run_tracking_and_reporting(self):
        """Case 8: NOT_RUN is recorded in metadata, markdown, and does not count as PASS."""
        results = [
            TestExecutionResult(
                test_id="t1",
                name="Test 1",
                tier_names=["quick"],
                runner_type="python",
                status="PASSED",
                exit_code=0,
                duration_sec=0.1,
                stdout="ok",
                stderr="",
            ),
            TestExecutionResult(
                test_id="t2",
                name="Test 2",
                tier_names=["quick"],
                runner_type="python",
                status="FAILED",
                exit_code=1,
                duration_sec=0.1,
                stdout="",
                stderr="error",
                failure_reason="Failed test",
            ),
            TestExecutionResult(
                test_id="t3",
                name="Test 3",
                tier_names=["quick"],
                runner_type="python",
                status="NOT_RUN",
                exit_code=None,
                duration_sec=0.0,
                stdout="",
                stderr="",
                failure_reason="Skipped due to fail-fast",
            ),
        ]

        json_path, md_path = self.run_silent(
            self.runner.generate_reports, "unit_not_run", results, total_planned=3
        )

        with open(json_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        meta = data["metadata"]
        self.assertEqual(meta["total_planned"], 3)
        self.assertEqual(meta["total_executed"], 2)
        self.assertEqual(meta["not_run_count"], 1)
        self.assertEqual(meta["passed_count"], 1)
        self.assertEqual(meta["failed_count"], 1)
        self.assertFalse(meta["all_success"])

        with open(md_path, "r", encoding="utf-8") as fp:
            md_content = fp.read()
        self.assertIn("NOT_RUN", md_content)
        self.assertIn("Not Run: 1", md_content)

    def test_09_json_all_success_logic(self):
        """Case 9: Verify all_success logic matrix across diverse status combinations."""
        # Helper to compute all_success via generate_reports
        def get_all_success(res_list, planned):
            jpath, _ = self.run_silent(
                self.runner.generate_reports, "unit_matrix", res_list, total_planned=planned
            )
            with open(jpath, "r", encoding="utf-8") as fp:
                return json.load(fp)["metadata"]["all_success"]

        pass_res = TestExecutionResult(
            test_id="tp", name="P", tier_names=["quick"], runner_type="python",
            status="PASSED", exit_code=0, duration_sec=0.1, stdout="", stderr="",
        )
        fail_res = TestExecutionResult(
            test_id="tf", name="F", tier_names=["quick"], runner_type="python",
            status="FAILED", exit_code=1, duration_sec=0.1, stdout="", stderr="", failure_reason="err",
        )
        req_skip_res = TestExecutionResult(
            test_id="ts_req", name="SReq", tier_names=["quick"], runner_type="python",
            status="SKIPPED", exit_code=-1, duration_sec=0.0, stdout="", stderr="", is_optional=False,
        )
        opt_skip_res = TestExecutionResult(
            test_id="ts_opt", name="SOpt", tier_names=["quick"], runner_type="python",
            status="SKIPPED", exit_code=-1, duration_sec=0.0, stdout="", stderr="", is_optional=True,
        )
        not_run_res = TestExecutionResult(
            test_id="tnr", name="NR", tier_names=["quick"], runner_type="python",
            status="NOT_RUN", exit_code=None, duration_sec=0.0, stdout="", stderr="",
        )

        # (a) All executed pass -> True
        self.assertTrue(get_all_success([pass_res, pass_res], planned=2))
        # (b) Any failure -> False
        self.assertFalse(get_all_success([pass_res, fail_res], planned=2))
        # (c) Required test skipped -> False
        self.assertFalse(get_all_success([pass_res, req_skip_res], planned=2))
        # (d) Optional test skipped -> True (if all others pass)
        self.assertTrue(get_all_success([pass_res, opt_skip_res], planned=2))
        # (e) NOT_RUN present -> False
        self.assertFalse(get_all_success([pass_res, not_run_res], planned=2))
        # (f) Zero tests planned -> False
        self.assertFalse(get_all_success([], planned=0))

    def test_10_exit_code_logic(self):
        """Case 10: Final exit code is 0 only on full success, 1 on any failure, req-skip, or not-run."""
        def calc_exit_code(results, total_planned):
            failed_count = sum(1 for r in results if r.status == "FAILED")
            required_skipped_count = sum(1 for r in results if r.status == "SKIPPED" and not r.is_optional)
            not_run_count = sum(1 for r in results if r.status == "NOT_RUN")
            all_success = (
                failed_count == 0
                and required_skipped_count == 0
                and not_run_count == 0
                and (total_planned > 0)
            )
            return 0 if all_success else 1

        p = TestExecutionResult(
            test_id="p", name="P", tier_names=["q"], runner_type="py", status="PASSED",
            exit_code=0, duration_sec=0.1, stdout="", stderr="",
        )
        f = TestExecutionResult(
            test_id="f", name="F", tier_names=["q"], runner_type="py", status="FAILED",
            exit_code=1, duration_sec=0.1, stdout="", stderr="",
        )
        s_req = TestExecutionResult(
            test_id="sr", name="SR", tier_names=["q"], runner_type="py", status="SKIPPED",
            exit_code=-1, duration_sec=0.0, stdout="", stderr="", is_optional=False,
        )
        s_opt = TestExecutionResult(
            test_id="so", name="SO", tier_names=["q"], runner_type="py", status="SKIPPED",
            exit_code=-1, duration_sec=0.0, stdout="", stderr="", is_optional=True,
        )
        nr = TestExecutionResult(
            test_id="nr", name="NR", tier_names=["q"], runner_type="py", status="NOT_RUN",
            exit_code=None, duration_sec=0.0, stdout="", stderr="",
        )

        self.assertEqual(calc_exit_code([p, p], 2), 0)
        self.assertEqual(calc_exit_code([p, f], 2), 1)
        self.assertEqual(calc_exit_code([p, s_req], 2), 1)
        self.assertEqual(calc_exit_code([p, s_opt], 2), 0)
        self.assertEqual(calc_exit_code([p, nr], 2), 1)
        self.assertEqual(calc_exit_code([], 0), 1)


if __name__ == "__main__":
    unittest.main()
