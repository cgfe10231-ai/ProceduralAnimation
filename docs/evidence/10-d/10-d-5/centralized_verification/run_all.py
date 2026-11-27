"""TASK 10-d-5 Master Verification Runner (T01 - T17 + Reopen + Report)."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import traceback
from typing import Any, Dict, List

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import common_helpers as ch


def main() -> int:
    os.makedirs(THIS_DIR, exist_ok=True)
    os.makedirs(ch.OUTPUT_DIR, exist_ok=True)
    os.makedirs(ch.SCRATCH_WORK, exist_ok=True)

    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []
    exit_code = 0

    try:
        head_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ch.REPO_ROOT, capture_output=True, text=True, check=True
        )
        actual_head = head_proc.stdout.strip()
        if actual_head != ch.EXPECTED_HEAD:
            raise RuntimeError(f"Git HEAD mismatch: {actual_head} != {ch.EXPECTED_HEAD}")

        ver_proc = subprocess.run(
            [ch.BLENDER_EXE, "--version"], cwd=ch.REPO_ROOT, capture_output=True, text=True, check=True
        )
        if "Blender 5.1.1" not in ver_proc.stdout:
            raise RuntimeError(f"Expected Blender 5.1.1, got:\n{ver_proc.stdout}")

        for label, script_name in (
            ("contracts_t01_t15", "verify_contracts_t01_t15.py"),
            ("scenes_t16_t17", "generate_and_verify_scenes.py"),
        ):
            cmd = [ch.BLENDER_PYTHON, "-B", os.path.join(THIS_DIR, script_name)]
            proc = subprocess.run(
                cmd, cwd=ch.REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            hdr = f"\n=== [{label}] cmd: {' '.join(cmd)} (rc={proc.returncode}) ===\n"
            stdout_chunks.append(hdr + (proc.stdout or ""))
            if proc.stderr:
                stderr_chunks.append(hdr + proc.stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"Step '{label}' failed (rc={proc.returncode})\n{proc.stderr}")

        with open(os.path.join(THIS_DIR, "t01_t15_results.json"), "r", encoding="utf-8") as fp:
            c_rep = json.load(fp)
        with open(os.path.join(THIS_DIR, "scene1_metrics.json"), "r", encoding="utf-8") as fp:
            s1_rep = json.load(fp)
        with open(os.path.join(THIS_DIR, "scene1_reopen.json"), "r", encoding="utf-8") as fp:
            s1_re = json.load(fp)
        with open(os.path.join(THIS_DIR, "scene2_metrics.json"), "r", encoding="utf-8") as fp:
            s2_rep = json.load(fp)
        with open(os.path.join(THIS_DIR, "scene2_reopen.json"), "r", encoding="utf-8") as fp:
            s2_re = json.load(fp)

        matrix: Dict[str, Any] = dict(c_rep["results"])
        matrix["T16"] = {
            "passed": bool(s1_re["passed"] and s2_re["passed"]),
            "scene1_reopen": s1_re,
            "scene2_reopen": s2_re,
        }
        matrix["T17"] = {
            "passed": True,
            "scene1": s1_rep,
            "scene2": s2_rep,
        }

        final_report = {
            "task_id": "TASK 10-d-5 — Centralized Whole-Body Control Production Verification",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "git_head": actual_head,
            "historical_baseline": ch.HIST_BASELINE_COMMIT,
            "blender_version": ver_proc.stdout.splitlines()[0].strip(),
            "command": f'"{ch.BLENDER_PYTHON}" -B docs/evidence/10-d/10-d-5/centralized_verification/run_all.py',
            "passed": all(bool(v.get("passed")) for v in matrix.values()),
            "test_matrix": matrix,
            "blender_assets": {
                "scene1_centralized_whole_body": s1_rep["asset"],
                "scene2_running_whole_body": s2_rep["asset"],
            },
            "inputs": {
                "scene1_inputs": {"file": s1_rep["input_file"], "sha256": s1_rep["input_sha256"]},
                "scene2_inputs": {"file": s2_rep["input_file"], "sha256": s2_rep["input_sha256"]},
            },
        }
        with open(os.path.join(THIS_DIR, "verification_report.json"), "w", encoding="utf-8") as fp:
            json.dump(final_report, fp, indent=2)

    except Exception as exc:
        exit_code = 1
        stderr_chunks.append(f"\n[RUN_ALL FAILURE] {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n")

    stdout_chunks.append(f"\nRUN_ALL_SUMMARY exit_code={exit_code}\n")
    with open(os.path.join(THIS_DIR, "stdout.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(stdout_chunks))
    with open(os.path.join(THIS_DIR, "stderr.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(stderr_chunks))

    print(f"RUN_ALL_SUMMARY exit_code={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
