# TASK 10-B-13: Production Transaction Code Coverage Gap Matrix

**Audit Round**: Round 4/5  
**Baseline Git Commit**: `ddaa9b8d796180076eaa3f5d79cde492df4ebb0a`  
**Target Architecture**: Six-Layer Transaction Engine (`src/rig/arm_ik.py`)

---

## 1. Coverage Gap Overview

During the joint audit of `src/rig/arm_ik.py` and its corresponding test suites (`tests/test_task10b_transaction_atomicity.py`, `tests/test_task10b_input_validation.py`, `tests/test_arm_ik_lifecycle_world_transform_contract.py`), all major execution paths were systematically checked for unproven branches, masked conditions, short-circuited logic, and missing boundary assertions.

---

## 2. Comprehensive Branch Coverage Analysis Matrix

| ID | Function Name | Line Range | Target Condition / Branch | Existing Tests | Current Status | Detailed Gap Description | Target Resolution in Round 5 |
|---|---|---|---|---|---|---|---|
| **GAP-01** | `verify_armature_deisolation_evidence` | 3959–3965 | `if record.get("recovery_state") == "RECOVERY_UNCERTAIN": return "RECOVERY_UNCERTAIN_REJECTED"` | `TEST-151` | **Short-Circuited** | `TEST-151` sets `snapshot_trusted: False`, causing premature exit at Line 3885 (`RECOVERY_EVIDENCE_INSUFFICIENT`). Line 3959 is never executed. | Refactor `TEST-151` to supply valid trusted snapshot; verify Line 3959 directly. |
| **GAP-02** | `_arm_rig_transaction` (Admission) | 4350–4364 | `if not id_check["is_valid"]:` when `id_check["status"] == "UNKNOWN"` | `TEST-138` | **Defective Branch** | Current code assumes all invalid checks imply `FAILED_D` (object death/destruction). `UNKNOWN` status is not distinguished from `ABSENT`. | Split branch: `ABSENT` $\to$ `FAILED_D`; `UNKNOWN` $\to$ `FAILED_C` or admission error without tombstone. |
| **GAP-03** | `_arm_rig_transaction` (Pre/Post Rollback) | 4420–4440, 4454–4465 | `if not id_check["is_valid"]:` when `id_check["status"] == "UNKNOWN"` during active exception | None | **Unproven** | When an exception occurs and object status is `UNKNOWN` (e.g. transient scene lock), system incorrectly creates a dead tombstone. | Add explicit test simulating transient lookup error during rollback; assert no tombstone created. |
| **GAP-04** | `_clear_or_retire_failure_isolation_by_coordinator` | 958–962 | `grant_candidate = authorization_grant if authorization_grant is not None else verification_evidence` | `TEST-133` | **Architectural Leak** | Fallback parameter allows caller to pass evidence instead of grant, weakening Layer 1 / Layer 2 boundary. | Require `authorization_grant` strictly; remove fallback; add rejection assertion. |
| **GAP-05** | `_arm_rig_transaction` (Nested Rollback) | 4280–4300 | Inner marks `rollback_only` and raises $E_1$; outer rollback raises $E_2$ | `TEST-119`, `TEST-121` | **Partial** | Only single-cause exception bubbling is checked; dual chained causes are not verified. | Add `TEST-174` asserting dual-exception cause chain (`__cause__` / `__context__`). |
| **GAP-06** | `retry_cleanup` | 3521–3538 | Shared `bpy.data.curves` and `bpy.data.armatures` refcount preservation | `TEST-82`, `TEST-83` | **Partial** | Only `bpy.data.meshes` is tested; other datablock pools (`curves`, `armatures`) lack direct assertions. | Add `TEST-175` asserting preservation of curves and armatures with `user_count > 0`. |
| **GAP-07** | `reset_arm_ik` | 4620–4670 | Multi-armature reset where Armature A is in `CLEANUP_PENDING` and Armature B is clean | `TEST-114` | **Partial** | Only single-armature global gate rejection is tested; cross-armature isolation under gate not asserted. | Add `TEST-176` asserting multi-armature selective cleanup gate behavior. |
| **GAP-08** | `_verify_dead_armature_tombstone_retirement_evidence` | 4080–4120 | Rejection of tombstone retirement when armature object still physically exists in `bpy.data.objects` | `TEST-155` | **Full** | Verified by `TEST-155` (living armature cannot retire tombstone). | No action required. |
| **GAP-09** | `_capture_pre_snapshot_structural_fingerprint` | 3150–3280 | Non-finite values (`NaN`, `Inf`) in deeply nested RNA collections | `TEST-165`–`TEST-173` | **Full** | Hardened and verified in Round 3 with 9 new tests. | No action required. |
| **GAP-10** | `_authorized_revert_relationship_record` | 2150–2210 | Rollback of `RELATIONSHIP_LINKED` when target collection was deleted mid-transaction | `TEST-88` | **Full** | Handled gracefully by checking collection liveness; verified in `TEST-88`. | No action required. |

---

## 3. Prioritized Gap Closure Action Plan for Round 5

1. **P1 Priority (F-01, F-02, F-03)**:
   - Close **GAP-01** (`TEST-151` short-circuit repair).
   - Close **GAP-02** & **GAP-03** (Disassociate `UNKNOWN` liveness from `FAILED-D` tombstone generation).
   - Close **GAP-04** (Remove parameter fallback; mandate strict Coordinator grant).
2. **P2 Priority (F-04, F-05, F-06)**:
   - Close **GAP-05** (`TEST-174` dual-exception chaining).
   - Close **GAP-06** (`TEST-175` shared non-mesh datablock preservation).
   - Close **GAP-07** (`TEST-176` multi-armature cleanup gate isolation).
