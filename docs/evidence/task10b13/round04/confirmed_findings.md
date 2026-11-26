# TASK 10-B-13: Confirmed Architectural & Code Findings Catalogue

**Audit Round**: Round 4/5  
**Baseline Git Commit**: `ddaa9b8d796180076eaa3f5d79cde492df4ebb0a`  
**Target Module**: `src/rig/arm_ik.py`, `tests/test_task10b_transaction_atomicity.py`

---

## 1. Summary of Findings

| ID | Title | Severity | P-Group | Architecture Layer | Production Impact | Proposed Action in Round 5 |
|---|---|---|---|---|---|---|
| **F-01** | `RECOVERY_UNCERTAIN` De-isolation Verification Short-Circuits in `TEST-151` | HIGH | P1 | Layer 1 / Layer 5 | High (Defect in test setup hides verification branch) | Fix test setup & enforce direct assertion on Case 1 Condition 6 |
| **F-02** | Object Liveness `UNKNOWN` State Erroneously Escalated to `FAILED-D` Tombstone | CRITICAL | P1 / P4 | Layer 1 / Layer 2 / Layer 4 | High (Transient error causes permanent object death declaration) | Disallow `FAILED-D` escalation for `UNKNOWN`; restrict `FAILED-D` strictly to `ABSENT` |
| **F-03** | Coordinator Grant Fallback Ambiguity & Unbounded Grant Accumulation | MEDIUM | P1 | Layer 2 | Medium (Contract signature permits ambiguous grant substitution) | Deprecate fallback, mandate explicit grant instance, add TTL / cleanup |
| **F-04** | Nested Transaction Dual-Exception Chaining Coverage Gap | LOW | P0 | Layer 1 | Low (Exception chaining tested for single cause only) | Add test verifying `__cause__` preservation during double exception |
| **F-05** | Non-Mesh DataBlock Shared Preservation Test Gap | LOW | P2 | Layer 2 / Layer 6 | Low (Only mesh datablocks tested for shared user_count preservation) | Add test for curve & armature shared datablock preservation |
| **F-06** | Dual-Arm Independent Reset Under `CLEANUP_PENDING` Gate Coverage Gap | LOW | P7 | Layer 1 / Layer 7 | Low (Bilateral reset tested, but cross-armature isolation under gate not tested) | Add multi-armature selective gate test |

---

## 2. Detailed Findings Documentation

### Finding F-01: `RECOVERY_UNCERTAIN` De-isolation Verification Short-Circuits in `TEST-151`
- **Location**:
  - `tests/test_task10b_transaction_atomicity.py` lines 2315–2360 (`test_151_failed_c_recovery_uncertain_forged_verified_rejected`)
  - `src/rig/arm_ik.py` lines 3880–3965 (`verify_armature_deisolation_evidence`)
- **Severity**: HIGH (Audit Finding / Coverage Gap)
- **Category**: P1 (Session Identity, FAILED Classification & De-Isolation Lifecycle)
- **Architectural Violation**:
  - `ARCHITECTURE_SYNC.md` Section 10.6.4 requires that when an armature is in `RECOVERY_UNCERTAIN` state, de-isolation must be strictly rejected even if structural snapshot comparison succeeds.
- **Root Cause Analysis**:
  In `test_151_failed_c_recovery_uncertain_forged_verified_rejected`, the test populates `_ISOLATED_FAILED_ARMATURES[session_id]` with:
  ```python
  "recovery_state": "RECOVERY_UNCERTAIN",
  "snapshot_trusted": False, # <--- Missing valid snapshot and trusted flag
  ```
  In `verify_armature_deisolation_evidence(session_id, evidence)`:
  Line 3883 checks Case 2 prerequisites:
  ```python
  if not record.get("snapshot_trusted", False) or not record.get("snapshot"):
      return VerificationEvidence(verdict="REJECTED", reason="RECOVERY_EVIDENCE_INSUFFICIENT", ...)
  ```
  Because `snapshot_trusted` is False, the function returns `REJECTED` with reason `RECOVERY_EVIDENCE_INSUFFICIENT` at line 3885!
  It **never reaches** line 3959:
  ```python
  if record.get("recovery_state") == "RECOVERY_UNCERTAIN":
      return VerificationEvidence(verdict="REJECTED", reason="RECOVERY_UNCERTAIN_REJECTED", ...)
  ```
  Therefore, the actual code branch implementing the `RECOVERY_UNCERTAIN` gate has zero test coverage and could be modified or broken without failing `TEST-151`.
- **Impact**:
  False confidence that `RECOVERY_UNCERTAIN` is independently guarded against de-isolation.
- **Remediation Plan for Round 5**:
  In Round 5, update `TEST-151` to supply a fully valid, trusted snapshot and matching current state, but with `recovery_state: "RECOVERY_UNCERTAIN"`. Assert that the verdict is `REJECTED` specifically with reason `RECOVERY_UNCERTAIN_REJECTED` (reaching line 3959).

---

### Finding F-02: Object Liveness `UNKNOWN` State Erroneously Escalated to `FAILED-D` Tombstone
- **Location**:
  - `src/rig/arm_ik.py` lines 4350–4364 (Admission check)
  - `src/rig/arm_ik.py` lines 4420–4440 (Pre-rollback check)
  - `src/rig/arm_ik.py` lines 4454–4465 (Post-rollback check)
  - `src/rig/arm_ik.py` lines 4487–4497 (Pre-ACTIVE SNAPSHOTTING check)
- **Severity**: CRITICAL (Architectural Defect)
- **Category**: P1 / P4
- **Architectural Violation**:
  - `ARCHITECTURE_SYNC.md` Section 10.6.2 and Section 10.6.3 mandate that `FAILED-D` is reserved strictly for physically destroyed, deleted, or unresolvable armatures whose identity is permanently unrecoverable (`ABSENT`).
  - Section 10.6.1 explicitly defines the tri-state liveness contract: `LIVE`, `ABSENT`, `UNKNOWN`. An `UNKNOWN` status indicates an indeterminate lookup condition (e.g. temporary context lock, transient collection hierarchy anomaly), and must **never** be interpreted as dead (`ABSENT`).
- **Root Cause Analysis**:
  In all 4 checkpoints of `_arm_rig_transaction`:
  ```python
  id_check = _check_original_object_liveness(armature, session_id)
  if not id_check["is_valid"]:
      _record_armature_failure_isolation_by_coordinator(
          armature,
          _FailedTransactionClass.FAILED_D, # <--- FORCED FAILED-D
          reason=id_check.get("reason", "ARMATURE_IDENTITY_INVALID_AT_ADMISSION")
      )
  ```
  `_check_original_object_liveness` returns:
  - `is_valid: True` only when `status == "LIVE"` and session/identity match.
  - `is_valid: False` when `status == "ABSENT"` OR `status == "UNKNOWN"`.
  When `status == "UNKNOWN"`, `id_check["is_valid"]` is False. The current code unconditionally escalates this to `_FailedTransactionClass.FAILED_D`, which registers the armature into `_DEAD_ARMATURE_TOMBSTONES`!
- **Impact**:
  A temporary failure to query an armature or collection immediately kills the armature's session, installs a dead tombstone, and prevents any further transactions on that object until a full dead armature retirement procedure is executed. This violates object safety and resilience.
- **Remediation Plan for Round 5**:
  In `_arm_rig_transaction`:
  Check `id_check["status"]`:
  - If `status == "ABSENT"`: Escalate to `FAILED_D` and install tombstone.
  - If `status == "UNKNOWN"`: Do NOT escalate to `FAILED_D`. Instead, classify as `FAILED_C` (`ISOLATED_FAILED_C`) or reject transaction admission with `ArmRigTransactionError("ARMATURE_LIVENESS_UNKNOWN")` without installing a tombstone in `_DEAD_ARMATURE_TOMBSTONES`.
  Add targeted regression tests in Round 5.

---

### Finding F-03: Coordinator Authorization Grant Parameter Fallback Ambiguity
- **Location**:
  - `src/rig/arm_ik.py` line 958 (`_clear_or_retire_failure_isolation_by_coordinator`)
  - `src/rig/arm_ik.py` lines 969–975
- **Severity**: MEDIUM (Architectural Hygiene / Security)
- **Category**: P1 / Layer 2
- **Architectural Violation**:
  - `ARCHITECTURE_SYNC.md` Section 10.7 defines strict authority boundaries: Layer 1 Coordinator issues grants; Layer 2 Registry validates and consumes grants. Layer 2 must not accept raw verification evidence in place of an authorization grant.
- **Root Cause Analysis**:
  Line 958 defines:
  ```python
  grant_candidate = authorization_grant if authorization_grant is not None else verification_evidence
  ```
  Allowing `authorization_grant` to fall back to `verification_evidence` blurs the separation of concerns between verification (Case 1) and authorization (Step 2). While `isinstance(grant_candidate, dict)` and `"grant_id" in grant_candidate` are checked, if a verification evidence object were ever structured as a dict with `grant_id`, it could bypass Coordinator grant issuance.
  Additionally, Coordinator grants lack an explicit expiration mechanism (TTL).
- **Impact**:
  Ambiguous calling convention; potential memory leak if unused grants accumulate in `_COORDINATOR_AUTHORIZATION_GRANTS`.
- **Remediation Plan for Round 5**:
  Require `authorization_grant` to be explicitly provided as a valid dictionary issued by `_issue_coordinator_authorization_grant`. Reject when `authorization_grant is None`. Add grant expiry timestamp checks (TTL) and eviction of stale grants.

---

### Finding F-04: Nested Transaction Dual-Exception Chaining Coverage Gap
- **Location**: `tests/test_task10b_transaction_atomicity.py`
- **Severity**: LOW (Coverage Gap)
- **Category**: P0 (Transaction Atomicity)
- **Details**:
  When an inner transaction marks `rollback_only` and raises an exception $E_1$, and the outer context during exit rollback encounters another exception $E_2$, both exceptions should be preserved via PEP 3134 (`raise E2 from E1` or chained `__context__`). Existing tests only test single exception bubbling.
- **Remediation Plan for Round 5**:
  Add `TEST-174` in Round 5 to explicitly assert exception chaining preservation.

---

### Finding F-05: Non-Mesh DataBlock Shared Preservation Test Gap
- **Location**: `tests/test_task10b_transaction_atomicity.py`
- **Severity**: LOW (Coverage Gap)
- **Category**: P2 (DataBlock Lifecycle)
- **Details**:
  `retry_cleanup` iterates through `("meshes", "curves", "lights", "cameras", "armatures", "lattices", "metaballs", "volumes")`. `TEST-82` and `TEST-83` only test `bpy.data.meshes`.
- **Remediation Plan for Round 5**:
  Add `TEST-175` verifying `bpy.data.curves` and `bpy.data.armatures` are not deleted during cleanup when their `user_count > 0`.

---

### Finding F-06: Dual-Arm Independent Reset Under `CLEANUP_PENDING` Gate Coverage Gap
- **Location**: `tests/test_task10b_transaction_atomicity.py`
- **Severity**: LOW (Coverage Gap)
- **Category**: P7 (Dual-Arm Coordination)
- **Details**:
  `reset_arm_ik` tests verify bilateral rollback when an arm fails. However, if Armature A is locked under `CLEANUP_PENDING`, Armature B (which is clean and independent) should either be able to reset independently or be explicitly isolated based on system policy.
- **Remediation Plan for Round 5**:
  Add `TEST-176` asserting multi-armature selective cleanup gate behavior.
