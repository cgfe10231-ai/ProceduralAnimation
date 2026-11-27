import os
import subprocess
import sys

REPO_ROOT = r"C:\Users\64701\OneDrive\Desktop\ProceduralAnimation"
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
PYTHON = r"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"
BASE = os.path.join(REPO_ROOT, "docs", "evidence", "12", "unified_verification")
HIST = os.path.join(BASE, "historical")
LOGS = os.path.join(BASE, "logs")
os.makedirs(HIST, exist_ok=True)
os.makedirs(LOGS, exist_ok=True)

t11_code = (
    "import sys; "
    "sys.path.insert(0, r'docs\\evidence\\11\\unified_verification'); "
    "import verify_footlock_contract as m; "
    "m.CONTRACT_RESULTS_JSON = r'docs\\evidence\\12\\unified_verification\\historical\\task11_footlock_results.json'; "
    "m.SCRATCH_REOPEN_DIR = r'C:\\Users\\64701\\.gemini\\antigravity\\brain\\195cba67-abc9-47a3-9c96-4bd0bab568e0\\scratch\\task12_reopen_task11'; "
    "raise SystemExit(m.main())"
)

jobs = [
    ("task12_continuous_motion", [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1", "--python", os.path.join(BASE, "verify_continuous_motion.py")], LOGS),
    ("task10b_wbc_failure", [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1", "--python", os.path.join(REPO_ROOT, "tests", "test_task10b_wbc_failure_contract.py")], HIST),
    ("task10d_contracts", [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1", "--python", os.path.join(REPO_ROOT, "docs", "evidence", "10-d", "10-d-5", "centralized_verification", "verify_contracts_t01_t15.py"), "--", "--worker", "contracts", "--out", os.path.join(HIST, "task10d_contracts_results.json")], HIST),
    ("task11_footlock", [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1", "--python-expr", t11_code], HIST),
]

rc_all = 0
for name, cmd, log_dir in jobs:
    print(f"=== RUNNING {name} ===", flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    open(os.path.join(log_dir, f"{name}.stdout.log"), "w", encoding="utf-8").write(proc.stdout or "")
    open(os.path.join(log_dir, f"{name}.stderr.log"), "w", encoding="utf-8").write(proc.stderr or "")
    tail = "\n".join((proc.stdout or "").splitlines()[-6:])
    print(f"{name} rc={proc.returncode}\n{tail}", flush=True)
    if proc.returncode != 0:
        rc_all = proc.returncode
        print("STDERR:\n" + (proc.stderr or "")[-1500:], flush=True)
        sys.exit(rc_all)

print("=== HISTORICAL_AND_CONTINUOUS_ALL_PASSED ===", flush=True)
