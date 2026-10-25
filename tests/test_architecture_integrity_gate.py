"""Architecture Documentation Integrity Gate Test (Task 6G-D-C2-FINAL).

Validates all architecture freeze documents for physical existence of referenced
Python modules, classes, methods, and enum members using AST index inspection.
Runs strictly read-only with zero file side effects.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.audit_c2_final_inspector import run_audit_verify_docs


def main() -> int:
    # Runs validator self-test suite (positive, negative, proposed, prose, dynamic, clause)
    # and all freeze documentation checks in strictly read-only mode with zero file side effects.
    ok, errors = run_audit_verify_docs(repo_root=REPO_ROOT)
    if not ok:
        print("[ARCHITECTURE GATE] Documentation integrity verification failed with errors:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[ARCHITECTURE GATE] PASS: All architecture documents verified. Zero phantom symbols found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
