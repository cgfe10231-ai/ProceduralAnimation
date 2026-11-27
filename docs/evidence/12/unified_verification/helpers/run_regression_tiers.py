import json
import os
import subprocess
import sys

REPO_ROOT = r"C:\Users\64701\OneDrive\Desktop\ProceduralAnimation"
PYTHON = r"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"
BASE = os.path.join(REPO_ROOT, "docs", "evidence", "12", "unified_verification")
RUNNER = os.path.join(REPO_ROOT, "tests", "run_test_suite.py")

tiers = ["quick", "physics", "motion", "full"]
summary = {}

for tier in tiers:
    out_dir = os.path.join(BASE, f"regression_{tier}")
    os.makedirs(out_dir, exist_ok=True)
    cmd = [PYTHON, RUNNER, "--tier", tier, "--fail-fast", "--output-dir", out_dir]
    print(f"=== RUNNING REGRESSION TIER: {tier.upper()} ===", flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    open(os.path.join(BASE, f"tier_{tier}_stdout.log"), "w", encoding="utf-8").write(proc.stdout or "")
    open(os.path.join(BASE, f"tier_{tier}_stderr.log"), "w", encoding="utf-8").write(proc.stderr or "")
    rep_path = os.path.join(out_dir, "test_report.json")
    counts = {}
    if os.path.isfile(rep_path):
        rep = json.load(open(rep_path, "r", encoding="utf-8"))
        for r in rep.get("results", []):
            st = r.get("status", "UNKNOWN")
            counts[st] = counts.get(st, 0) + 1
    summary[tier] = {"rc": proc.returncode, "counts": counts}
    print(f"TIER {tier}: rc={proc.returncode} counts={counts}", flush=True)
    if proc.returncode != 0:
        print("\n".join((proc.stdout or "").splitlines()[-40:]), flush=True)
        print("STDERR:\n" + (proc.stderr or "")[-1500:], flush=True)
        sys.exit(proc.returncode)

print("ALL_4_REGRESSION_TIERS_PASSED:", json.dumps(summary), flush=True)
