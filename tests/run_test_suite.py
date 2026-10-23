"""Unified Test Runner and Multi-Tier Orchestrator (Task 6G-D-PRE-P1).

Provides a single controlled entry point for test execution across all subsystems:
- Dispatches sub-tests internally without requiring per-test terminal approvals.
- Dynamically resolves Blender 5.1.1 and the active Python environment.
- Enforces per-test timeout and process-tree termination on Windows.
- Implements strict failure detection (non-zero exit, timeout, and stdout pattern checking).
- Generates unified reports: `tests/output/test_report.json` and `test_report.md`.
"""

import argparse
from dataclasses import dataclass
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.test_registry import (
    RunnerType,
    TestDefinition,
    TestTier,
    find_test_by_id,
    get_all_registered_tests,
    get_tests_for_tier,
)


# =============================================================================
# Environment Resolution Helpers
# =============================================================================

def resolve_blender_executable() -> str:
    """Locate Blender 5.1 / 5.0 executable without altering system environment."""
    candidates = [
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("blender")
    if found:
        return found
    raise FileNotFoundError("Blender executable could not be located in standard paths or PATH.")


def resolve_python_executable() -> str:
    """Locate real Python interpreter, avoiding zero-byte Windows Store stubs."""
    current = sys.executable
    if current and os.path.isfile(current) and "WindowsApps" not in current:
        return current
    candidates = [
        r"C:\Users\64701\AppData\Local\Python\bin\python.exe",
        r"C:\Program Files\Python314\python.exe",
        r"C:\Program Files\Python312\python.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("python")
    if found and "WindowsApps" not in found:
        return found
    return sys.executable


def kill_process_tree(pid: int) -> None:
    """Forcefully kill process and all its children on Windows to eliminate zombie Blenders."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


# =============================================================================
# Failure Pattern Detection
# =============================================================================

FAILURE_REGEX = re.compile(
    r"(?:^|\n)\s*(?:\[FAIL\]|\[FAILED\]|Traceback \(most recent call last\)|AssertionError:|Error: |ValueError: |RuntimeError: )",
    re.IGNORECASE,
)

FALSE_FAILURE_WHITELIST = [
    "0 unreachable events",
    "0 times",
    "0 unmet",
    "0 failure",
    "0 errors",
    "no error",
    "0 rom violations",
]


def detect_failure_in_output(stdout: str, stderr: str) -> Optional[str]:
    """Inspect stdout and stderr for explicit failure indicators even if returncode was 0."""
    combined = f"{stdout}\n{stderr}"
    matches = FAILURE_REGEX.findall(combined)
    if matches:
        for line in combined.splitlines():
            line_str = line.strip()
            if any(w in line_str.lower() for w in FALSE_FAILURE_WHITELIST):
                continue
            if any(m.strip().lower() in line_str.lower() for m in matches):
                return f"Failure pattern detected in output: '{line_str}'"
    return None


# =============================================================================
# Test Runner Core
# =============================================================================

@dataclass
class TestExecutionResult:
    test_id: str
    name: str
    tier_names: List[str]
    runner_type: str
    status: str  # PASSED, AUTOMATED_PASS, FAILED, TIMEOUT, SKIPPED
    exit_code: Optional[int]
    duration_sec: float
    stdout: str
    stderr: str
    failure_reason: Optional[str] = None
    is_visual_acceptance: bool = False


class TestSuiteRunner:
    """Manages multi-test sequencing, resource isolation, and reporting."""

    def __init__(
        self,
        blender_bin: str,
        python_bin: str,
        output_dir: str,
        timeout_multiplier: float = 1.0,
        fail_fast: bool = False,
    ):
        self.blender_bin = blender_bin
        self.python_bin = python_bin
        self.output_dir = output_dir
        self.timeout_multiplier = timeout_multiplier
        self.fail_fast = fail_fast
        os.makedirs(self.output_dir, exist_ok=True)

    def execute_test(self, test: TestDefinition) -> TestExecutionResult:
        """Run an individual test definition under process isolation and timeout supervision."""
        print(f"\n[{test.test_id}] Starting: {test.name}")
        full_script = os.path.join(PROJECT_ROOT, test.script_path)
        effective_timeout = test.timeout_sec * self.timeout_multiplier

        # Build command based on runner type
        if test.runner_type == RunnerType.PYTHON:
            cmd = [self.python_bin, full_script]
        elif test.runner_type == RunnerType.BLENDER_HEADLESS:
            cmd = [self.blender_bin, "-b", "-P", full_script]
        elif test.runner_type == RunnerType.BLENDER_WITH_BLEND:
            if not test.target_blend:
                return TestExecutionResult(
                    test_id=test.test_id,
                    name=test.name,
                    tier_names=[t.value for t in test.tiers],
                    runner_type=test.runner_type.value,
                    status="SKIPPED",
                    exit_code=-1,
                    duration_sec=0.0,
                    stdout="",
                    stderr="Missing target_blend definition",
                    failure_reason="Configuration error: target_blend required",
                )
            full_blend = os.path.join(PROJECT_ROOT, test.target_blend)
            if not os.path.isfile(full_blend):
                return TestExecutionResult(
                    test_id=test.test_id,
                    name=test.name,
                    tier_names=[t.value for t in test.tiers],
                    runner_type=test.runner_type.value,
                    status="SKIPPED",
                    exit_code=-1,
                    duration_sec=0.0,
                    stdout="",
                    stderr=f"Required target blend not found: {test.target_blend}",
                    failure_reason=f"Target blend file missing: {test.target_blend}",
                )
            cmd = [self.blender_bin, "-b", full_blend, "-P", full_script]
        else:
            raise ValueError(f"Unknown runner_type: {test.runner_type}")

        print(f"  Command: {' '.join(cmd)}")
        start_time = time.time()
        stdout_str = ""
        stderr_str = ""
        exit_code = 0
        timed_out = False

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_ROOT,
            )
            stdout_str, stderr_str = proc.communicate(timeout=effective_timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc.pid)
            try:
                stdout_str, stderr_str = proc.communicate(timeout=5.0)
            except Exception:
                pass
            exit_code = -999

        duration = round(time.time() - start_time, 2)

        # Evaluate Pass / Fail state
        if timed_out:
            status = "FAILED"
            fail_reason = f"Execution timed out after {effective_timeout:.1f}s"
            print(f"  [TIMEOUT] {fail_reason} ({duration}s)")
        elif exit_code != 0:
            status = "FAILED"
            fail_reason = f"Process exited with non-zero code {exit_code}"
            print(f"  [FAIL] {fail_reason} ({duration}s)")
        else:
            # Check for hidden failure text in output
            output_err = detect_failure_in_output(stdout_str, stderr_str)
            if output_err:
                status = "FAILED"
                fail_reason = output_err
                print(f"  [FAIL] {fail_reason} (exit_code was 0, but failure pattern detected) ({duration}s)")
            else:
                if test.is_visual_acceptance:
                    status = "AUTOMATED_PASS"
                    fail_reason = None
                    print(f"  [AUTOMATED_PASS] Test passed automation (Visual Inspection Required) ({duration}s)")
                else:
                    status = "PASSED"
                    fail_reason = None
                    print(f"  [PASS] Test completed successfully ({duration}s)")

        return TestExecutionResult(
            test_id=test.test_id,
            name=test.name,
            tier_names=[t.value for t in test.tiers],
            runner_type=test.runner_type.value,
            status=status,
            exit_code=exit_code,
            duration_sec=duration,
            stdout=stdout_str,
            stderr=stderr_str,
            failure_reason=fail_reason,
            is_visual_acceptance=test.is_visual_acceptance,
        )

    def run_suite(self, tests: List[TestDefinition]) -> List[TestExecutionResult]:
        """Execute a collection of tests in sequence, supporting fail-fast."""
        results: List[TestExecutionResult] = []
        for test in tests:
            res = self.execute_test(test)
            results.append(res)
            if self.fail_fast and res.status == "FAILED":
                print(f"\n[FAIL-FAST] Halting test suite execution after failure on '{test.test_id}'.")
                break
        return results

    def generate_reports(
        self,
        tier_label: str,
        results: List[TestExecutionResult],
        total_planned: int,
    ) -> Tuple[str, str]:
        """Generate structured JSON and Markdown summary reports."""
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        passed_count = sum(1 for r in results if r.status in ("PASSED", "AUTOMATED_PASS"))
        failed_count = sum(1 for r in results if r.status == "FAILED")
        skipped_count = sum(1 for r in results if r.status == "SKIPPED")
        auto_pass_count = sum(1 for r in results if r.status == "AUTOMATED_PASS")
        total_time = round(sum(r.duration_sec for r in results), 2)

        # 1. JSON Report
        json_path = os.path.join(self.output_dir, "test_report.json")
        json_payload = {
            "metadata": {
                "generated_at": timestamp_str,
                "tier": tier_label,
                "total_planned": total_planned,
                "total_executed": len(results),
                "passed_count": passed_count,
                "automated_pass_count": auto_pass_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "total_duration_sec": total_time,
                "all_success": (failed_count == 0),
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "name": r.name,
                    "tier_names": r.tier_names,
                    "runner_type": r.runner_type,
                    "status": r.status,
                    "exit_code": r.exit_code,
                    "duration_sec": r.duration_sec,
                    "failure_reason": r.failure_reason,
                    "is_visual_acceptance": r.is_visual_acceptance,
                    "stdout_tail": r.stdout[-1500:] if r.stdout else "",
                    "stderr_tail": r.stderr[-1500:] if r.stderr else "",
                }
                for r in results
            ],
        }
        with open(json_path, "w", encoding="utf-8") as fp:
            json.dump(json_payload, fp, indent=2, ensure_ascii=False)

        # 2. Markdown Report
        md_path = os.path.join(self.output_dir, "test_report.md")
        md_lines = [
            "# ProceduralAnimation Test Execution Report",
            f"\n> **Execution Date**: {timestamp_str}  ",
            f"> **Target Tier**: `{tier_label}`  ",
            f"> **Overall Result**: {'**ALL PASSED**' if failed_count == 0 else '**FAILED**'}  ",
            f"> **Execution Summary**: Total: {len(results)}/{total_planned} | Passed: {passed_count} (Automated Pass: {auto_pass_count}) | Failed: {failed_count} | Skipped: {skipped_count} | Duration: {total_time:.2f}s",
            "\n---",
            "\n## Test Results Table\n",
            "| Test ID | Test Name | Runner | Status | Duration | Failure / Notes |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for r in results:
            note = r.failure_reason if r.failure_reason else ("Visual Inspection Required" if r.is_visual_acceptance else "-")
            status_badge = f"**{r.status}**" if r.status in ("PASSED", "AUTOMATED_PASS") else f"<span style='color:red;'>**{r.status}**</span>"
            md_lines.append(
                f"| `{r.test_id}` | {r.name} | `{r.runner_type}` | {status_badge} | {r.duration_sec}s | {note} |"
            )

        if failed_count > 0:
            md_lines.append("\n## Failure Details\n")
            for r in results:
                if r.status == "FAILED":
                    md_lines.append(f"### `{r.test_id}`: {r.name}")
                    md_lines.append(f"- **Failure Reason**: {r.failure_reason}")
                    md_lines.append(f"- **Exit Code**: {r.exit_code}")
                    md_lines.append(f"- **Duration**: {r.duration_sec}s")
                    if r.stderr:
                        md_lines.append(f"```\n[STDERR]\n{r.stderr[-1000:]}\n```")
                    if r.stdout and not r.stderr:
                        md_lines.append(f"```\n[STDOUT TAIL]\n{r.stdout[-1000:]}\n```")

        with open(md_path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(md_lines))

        return json_path, md_path


# =============================================================================
# CLI Main Entry Point
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="ProceduralAnimation Unified Test Runner (Task 6G-D-PRE-P1)")
    parser.add_argument(
        "--tier",
        type=str,
        default="quick",
        choices=["quick", "physics", "motion", "full", "legacy"],
        help="Target test tier category to execute.",
    )
    parser.add_argument("--test-id", type=str, default=None, help="Execute a single specific test by its unique ID.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop execution immediately upon first failure.")
    parser.add_argument(
        "--timeout-multiplier",
        type=float,
        default=1.0,
        help="Multiplier for per-test timeout durations (default: 1.0).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(PROJECT_ROOT, "tests", "output"),
        help="Directory to save test_report.json and test_report.md.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print selected tests without executing them.")

    args = parser.parse_args()

    print("=" * 80)
    print("PROCEDURAL ANIMATION: UNIFIED TEST SUITE RUNNER")
    print(f"Target Tier: {args.tier.upper()} | Fail-Fast: {args.fail_fast}")
    print("=" * 80)

    # 1. Resolve test list
    if args.test_id:
        single_test = find_test_by_id(args.test_id)
        if not single_test:
            print(f"[ERROR] Test ID '{args.test_id}' not found in registry.", file=sys.stderr)
            return 1
        tests_to_run = [single_test]
        tier_label = f"single:{args.test_id}"
    else:
        target_tier = TestTier(args.tier)
        tests_to_run = get_tests_for_tier(target_tier)
        tier_label = args.tier

    print(f"\nResolved {len(tests_to_run)} test suite(s) to execute:")
    for idx, t in enumerate(tests_to_run, 1):
        print(f"  {idx:02d}. [{t.test_id}] {t.name} ({t.runner_type.value}, timeout={t.timeout_sec}s)")

    if args.dry_run:
        print("\n[DRY-RUN] Test plan validated. Halting without execution.")
        return 0

    # 2. Resolve tools
    blender_exe = resolve_blender_executable()
    python_exe = resolve_python_executable()
    print(f"\nExecution Toolchain:")
    print(f"  - Blender: {blender_exe}")
    print(f"  - Python:  {python_exe}")

    runner = TestSuiteRunner(
        blender_bin=blender_exe,
        python_bin=python_exe,
        output_dir=args.output_dir,
        timeout_multiplier=args.timeout_multiplier,
        fail_fast=args.fail_fast,
    )

    # 3. Execute
    results = runner.run_suite(tests_to_run)

    # 4. Generate Reports
    json_rep, md_rep = runner.generate_reports(tier_label, results, len(tests_to_run))

    # 5. Print Summary
    passed_count = sum(1 for r in results if r.status in ("PASSED", "AUTOMATED_PASS"))
    failed_count = sum(1 for r in results if r.status == "FAILED")
    skipped_count = sum(1 for r in results if r.status == "SKIPPED")
    total_time = round(sum(r.duration_sec for r in results), 2)

    print("\n" + "=" * 80)
    print(f"TEST SUITE EXECUTION COMPLETED IN {total_time}s")
    print(f"Total: {len(results)} | Passed: {passed_count} | Failed: {failed_count} | Skipped: {skipped_count}")
    print(f"Reports Written:")
    print(f"  - JSON: {json_rep}")
    print(f"  - Markdown: {md_rep}")
    print("=" * 80)

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
