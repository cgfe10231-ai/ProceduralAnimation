# Task 10-B-8: Baseline & Environment Record

- **Task ID**: `TASK 10-B-8: Full Transaction Lifecycle & Ownership Integrity Repair`
- **Component**: `src/rig/arm_ik.py`
- **Test Suites**:
  - `tests/test_task10b_input_validation.py` (TEST-01 to TEST-30)
  - `tests/test_task10b_transaction_atomicity.py` (TEST-31 to TEST-102)
- **Base Commit**: `445f0e0ebc6459a69527bab329548a6ad182493d` (from `origin/audit/task-10-b-7`)
- **Target Branch**: `audit/task-10-b-8`
- **Blender Version**: 5.1.1 (hash `b70da489d7f4`, built 2026-04-14 01:37:22)
- **Python Runtime**: Python 3.11.11 (embedded in Blender 5.1)
- **OS Platform**: Windows 11 (AMD64)
- **Execution Date**: 2026-11-06

## Invariants Preserved
- `INV-01 (Strict Identity)`: Objects in snapshot are verified and restored strictly by pointer identity; name matching alone never proves identity.
- `INV-02 (Ownership Bounds)`: Transactions delete only resources explicitly registered as transaction-owned (`created_controller_objects`, `created_collections`, `stashed_objects`, `stashed_constraints`).
- `INV-03 (Immediate Ownership Registration)`: Newly created controllers register ownership immediately after `bpy.data.objects.new()` before any subsequent collection linking or transform setup.
- `INV-04 (Post-Commit Irreversible Cleanup)`: Any exception occurring after logical commit (`COMMITTED`) enters Phase 3 cleanup failure handling, transitions to `CLEANUP_PENDING`, registers the transaction, and prohibits ordinary rollback.
- `INV-05 (Cleanup Admission Gate)`: An unresolved cleanup pending transaction blocks new write transactions on that Armature while allowing unrelated Armatures.
- `INV-06 (External Resource Preservation)`: External objects, collections, and datablocks added during transaction execution are never unlinked or removed.
- `INV-07 (Protected Files)`: `ARCHITECTURE.md`, `DECISIONS.md`, and `ARCHITECTURE_SYNC.md` Section 4.2.3 are untouched; `P2_R1_recovery.patch` preserved untracked.
