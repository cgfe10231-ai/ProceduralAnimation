# TASK 10-B-13: Minimal Fault Reproductions & Evidence Cases

**Audit Round**: Round 4/5  
**Baseline Git Commit**: `ddaa9b8d796180076eaa3f5d79cde492df4ebb0a`

---

## 1. Reproduction Case F-01: `RECOVERY_UNCERTAIN` De-isolation Short-Circuit

### 1.1 Fault Description
In `tests/test_task10b_transaction_atomicity.py`, `TEST-151` verifies rejection of de-isolation for an armature marked with `recovery_state: "RECOVERY_UNCERTAIN"`. However, the test fixtures omit a valid snapshot and set `snapshot_trusted: False`. As a result, the function exits early at Case 2 instead of executing the dedicated `RECOVERY_UNCERTAIN` rejection logic.

### 1.2 Reproduction Code Snippet
```python
# Minimal reproduction showing short-circuit vs intended check
from src.rig.arm_ik import (
    _ISOLATED_FAILED_ARMATURES,
    verify_armature_deisolation_evidence,
)

session_id = "test-session-f01"
# Case A: Current TEST-151 setup (snapshot_trusted is False or omitted)
_ISOLATED_FAILED_ARMATURES[session_id] = {
    "session_id": session_id,
    "original_object_name": "TestArmature",
    "failure_class": "FAILED_C",
    "recovery_state": "RECOVERY_UNCERTAIN",
    "snapshot_trusted": False, # <--- Triggers premature exit!
    "snapshot": None,
}

evidence = {"session_id": session_id, "structural_snapshot": {}}
result_a = verify_armature_deisolation_evidence(session_id, evidence)

# Actual Result in Case A:
print("Case A Result:", result_a.verdict, result_a.reason)
# Output: REJECTED, RECOVERY_EVIDENCE_INSUFFICIENT (Line 3885)
# Note: Line 3959 (RECOVERY_UNCERTAIN_REJECTED) is NEVER reached!

# Case B: Correct setup with trusted snapshot
_ISOLATED_FAILED_ARMATURES[session_id]["snapshot_trusted"] = True
_ISOLATED_FAILED_ARMATURES[session_id]["snapshot"] = {"bones": {}}
# With valid object and matching fingerprint:
# Line 3959 is reached:
# Output should be: REJECTED, RECOVERY_UNCERTAIN_REJECTED
```

### 1.3 Expected vs. Actual Behavior
- **Actual**: Test passes because verdict is `REJECTED`, but the reason is `RECOVERY_EVIDENCE_INSUFFICIENT`.
- **Expected**: Test should pass because verdict is `REJECTED` and reason is specifically `RECOVERY_UNCERTAIN_REJECTED`.

---

## 2. Reproduction Case F-02: `UNKNOWN` Liveness Erroneously Escalated to `FAILED-D` Tombstone

### 2.1 Fault Description
When `_check_original_object_liveness` returns `status == "UNKNOWN"`, `id_check["is_valid"]` is `False`. In `_arm_rig_transaction`, any `not id_check["is_valid"]` is unconditionally escalated to `_FailedTransactionClass.FAILED_D`, which permanently places the armature into `_DEAD_ARMATURE_TOMBSTONES`.

### 2.2 Reproduction Code Snippet
```python
from unittest.mock import patch
import bpy
from src.rig.arm_ik import (
    _arm_rig_transaction,
    _DEAD_ARMATURE_TOMBSTONES,
    _ISOLATED_FAILED_ARMATURES,
    ensure_armature_session_identity,
)

armature = bpy.data.objects.get("TestArmature")
session_id = ensure_armature_session_identity(armature)

# Simulate transient lookup error returning UNKNOWN liveness
with patch("src.rig.arm_ik._check_original_object_liveness") as mock_liveness:
    mock_liveness.return_value = {
        "is_valid": False,
        "status": "UNKNOWN",
        "reason": "TRANSIENT_HIERARCHY_LOCK",
    }

    try:
        with _arm_rig_transaction(armature):
            pass
    except Exception as exc:
        print("Transaction failed as expected:", exc)

# Check registries:
is_in_tombstones = session_id in _DEAD_ARMATURE_TOMBSTONES
is_in_isolated = session_id in _ISOLATED_FAILED_ARMATURES

print("In Dead Tombstones (BUG):", is_in_tombstones)
print("In Isolated FAILED-C (EXPECTED):", is_in_isolated)
```

### 2.3 Expected vs. Actual Behavior
- **Actual**: `is_in_tombstones` is `True`. The armature object is permanently marked as dead, and can never be used again without tombstone retirement.
- **Expected**: `is_in_tombstones` must be `False`. `UNKNOWN` status indicates indeterminate condition, NOT physical destruction. It must be classified as `FAILED-C` (or transaction admission rejection) without installing a tombstone in `_DEAD_ARMATURE_TOMBSTONES`.

---

## 3. Reproduction Case F-03: Coordinator Grant Parameter Fallback Ambiguity

### 3.1 Fault Description
In `_clear_or_retire_failure_isolation_by_coordinator`:
```python
grant_candidate = (
    authorization_grant
    if authorization_grant is not None
    else verification_evidence
)
```
If a caller supplies `authorization_grant=None` and passes a mock dict with `"grant_id"` as `verification_evidence`, the parameter fallback allows the check to proceed against `verification_evidence`, blurring the separation between evidence verification and grant issuance.

### 3.2 Reproduction Code Snippet
```python
# Demonstration of parameter ambiguity:
fake_grant = {"grant_id": "forged_id", "consumed": False}

# Caller calls with authorization_grant=None, but passes fake_grant as verification_evidence:
# _clear_or_retire_failure_isolation_by_coordinator(
#     session_id,
#     verification_evidence=fake_grant,
#     authorization_grant=None
# )
# grant_candidate falls back to fake_grant instead of failing immediately with:
# ValueError("authorization_grant must be explicitly provided")
```

### 3.3 Expected vs. Actual Behavior
- **Actual**: Method accepts `verification_evidence` as `grant_candidate` if `authorization_grant` is `None`.
- **Expected**: Method must enforce `authorization_grant is not None` and type-check it against Coordinator-issued grant structure.
